"""
audio_bridge.py — 多机器人双向对讲桥

架构：
  电脑麦克风 ─(sounddevice input callback, audio thread)─►
      对每个活动通话的 MicFanoutTrack 做扇出（每 track 一份 int16 帧）
        ─(asyncio.Queue via call_soon_threadsafe)─►
          MicFanoutTrack.recv()  ← aiortc 按 20ms 节奏拉帧
            ─► 编码 ─► RTP ─► 机器狗

  机器狗麦克风 ─► RTP ─► aiortc decoded AudioFrame
      ─► AudioBridge._on_robot_frame(robot_id, frame)
        ─► 写入该 robot 的 RingBuffer（thread-safe）
          ─(sounddevice output callback, audio thread)─►
            所有活动 robot 的 buffer 混音（简单求和 + clip）
              ─► 电脑扬声器

关键设计：
  * 单个 mic 输入流 / 单个 speaker 输出流；无论多少台狗都只开一次
  * 会话动态注册：第一台狗开通话时懒启动 sounddevice，最后一台关时停
  * mute + volume 是全局旋钮，不阻塞 RTP 流（静音时发零帧，保持 SRTP 会话活跃）
  * 断线兜底：unregister 会清空 track 队列 + 关闭 track，避免残留任务
  * 所有跨线程状态用锁；alsa/coreaudio 打开失败时抛清晰错误，UI 层可捕获
"""

from __future__ import annotations

import asyncio
import fractions
import logging
import threading
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger("MultiRobotApp.audio")

# ─── 依赖延迟导入，避免主进程启动就失败 ───
try:
    import sounddevice as _sd
    _SD_OK = True
except Exception as e:
    _sd = None
    _SD_OK = False
    logger.warning("sounddevice 不可用，对讲功能不可用：%s", e)

try:
    import av as _av
    from aiortc import MediaStreamTrack
    from aiortc.mediastreams import MediaStreamError
    _AV_OK = True
except Exception as e:
    _av = None
    MediaStreamTrack = object  # type: ignore
    MediaStreamError = Exception  # type: ignore
    _AV_OK = False
    logger.warning("aiortc/av 不可用，对讲功能不可用：%s", e)


# WebRTC 音频协商基本上都收敛到 48kHz stereo；机器狗也是这个格式。
SAMPLE_RATE = 48000
CHANNELS = 2
FRAME_MS = 20
SAMPLES_PER_FRAME = SAMPLE_RATE * FRAME_MS // 1000   # 960
# 播放/发送 ring buffer 的容量（毫秒）。太小容易 underrun，太大延迟高。
RING_BUFFER_MS = 400
RING_BUFFER_SAMPLES = SAMPLE_RATE * RING_BUFFER_MS // 1000
# 发送侧队列上限（帧），~160ms 抖动余量
MIC_QUEUE_MAX = 8


class AudioBridgeError(RuntimeError):
    """AudioBridge 不可用 / 打开设备失败等错误。"""


# ─────────────────────────────────────────────────────────────
# RingBuffer — thread-safe int16 stereo circular buffer
# ─────────────────────────────────────────────────────────────
class _RingBuffer:
    """写入端可能来自任意线程；读取端来自 sounddevice output 回调线程。
    满时丢最老的数据（保证低延迟；宁可断音也不允许音频回声性拉长）。"""

    def __init__(self, capacity_samples: int = RING_BUFFER_SAMPLES,
                 channels: int = CHANNELS):
        self._buf = np.zeros((capacity_samples, channels), dtype=np.int16)
        self._cap = capacity_samples
        self._channels = channels
        self._w = 0
        self._r = 0
        self._avail = 0
        self._lock = threading.Lock()

    def write(self, chunk: np.ndarray):
        """chunk: (N, channels) int16"""
        if chunk.ndim == 1:
            chunk = chunk.reshape(-1, 1)
            if self._channels == 2:
                chunk = np.repeat(chunk, 2, axis=1)
        if chunk.shape[1] != self._channels:
            return
        n = chunk.shape[0]
        if n == 0:
            return
        with self._lock:
            if self._avail + n > self._cap:
                overflow = self._avail + n - self._cap
                self._r = (self._r + overflow) % self._cap
                self._avail -= overflow
            end = self._w + n
            if end <= self._cap:
                self._buf[self._w:end] = chunk
            else:
                first = self._cap - self._w
                self._buf[self._w:] = chunk[:first]
                self._buf[:n - first] = chunk[first:]
            self._w = end % self._cap
            self._avail += n

    def read(self, n: int) -> np.ndarray:
        """返回长度恰好 n 的 (n, channels) int16 数组；缓冲不足处补零。"""
        out = np.zeros((n, self._channels), dtype=np.int16)
        with self._lock:
            take = min(n, self._avail)
            if take > 0:
                end = self._r + take
                if end <= self._cap:
                    out[:take] = self._buf[self._r:end]
                else:
                    first = self._cap - self._r
                    out[:first] = self._buf[self._r:]
                    out[first:take] = self._buf[:take - first]
                self._r = end % self._cap
                self._avail -= take
        return out

    def clear(self):
        with self._lock:
            self._w = 0
            self._r = 0
            self._avail = 0


# ─────────────────────────────────────────────────────────────
# MicFanoutTrack — 每个通话一个，向机器狗推送本机麦克风帧
# ─────────────────────────────────────────────────────────────
if _AV_OK:

    class MicFanoutTrack(MediaStreamTrack):
        """aiortc 会持续调用 recv() 拉帧。我们从 asyncio.Queue 获取；
        队列由 AudioBridge 的 mic 回调（audio 线程）通过 call_soon_threadsafe 填充。"""

        kind = "audio"
        _TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

        def __init__(self, loop: asyncio.AbstractEventLoop):
            super().__init__()
            self._loop = loop
            self._queue: asyncio.Queue = asyncio.Queue(maxsize=MIC_QUEUE_MAX)
            self._pts = 0
            self._closed = False

        async def recv(self):
            if self._closed:
                raise MediaStreamError
            try:
                # 等 mic callback 塞数据；超时是为了防止对端断开时永久 hang。
                chunk = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                # mic 好像挂了 —— 发一帧静音顶住，保持 SRTP 会话
                chunk = np.zeros((SAMPLES_PER_FRAME, CHANNELS), dtype=np.int16)

            if chunk is None:
                raise MediaStreamError

            # 构建 av.AudioFrame（packed s16 stereo）
            samples = chunk.shape[0]
            frame = _av.AudioFrame(format="s16", layout="stereo", samples=samples)
            frame.sample_rate = SAMPLE_RATE
            frame.pts = self._pts
            frame.time_base = self._TIME_BASE
            # 交织 int16：AudioFrame 的 plane 0 就是 packed s16
            frame.planes[0].update(chunk.astype(np.int16).tobytes())
            self._pts += samples
            return frame

        def push(self, chunk: np.ndarray):
            """从 audio 线程调用。"""
            if self._closed or self._loop.is_closed():
                return
            try:
                self._loop.call_soon_threadsafe(self._enqueue_or_drop, chunk)
            except RuntimeError:
                # 循环已停
                pass

        def _enqueue_or_drop(self, chunk):
            if self._closed:
                return
            q = self._queue
            if q.full():
                try:
                    q.get_nowait()   # 丢最老
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(chunk)
            except asyncio.QueueFull:
                pass

        def close(self):
            self._closed = True
            # 塞个哨兵让在等的 recv() 立刻醒过来
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            except RuntimeError:
                pass
            try:
                self.stop()
            except Exception:
                pass

else:
    class MicFanoutTrack:   # type: ignore
        def __init__(self, *a, **kw):
            raise AudioBridgeError("aiortc / av 不可用，无法创建音频轨")


# ─────────────────────────────────────────────────────────────
# AudioBridge — 全局单例，管理 sd 输入/输出流 + 每台狗的 session
# ─────────────────────────────────────────────────────────────
class _Session:
    __slots__ = ("track", "playback_buf", "sender", "conn")

    def __init__(self, track, playback_buf, sender, conn):
        self.track = track
        self.playback_buf = playback_buf
        self.sender = sender          # aiortc RTCRtpSender（addTrack 返回值）
        self.conn = conn              # UnitreeWebRTCConnection


class AudioBridge:
    """全局单例。所有活动的 robot 通话通过它复用同一对 sd 流。"""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        if not _SD_OK:
            raise AudioBridgeError("sounddevice 未安装或无法加载")
        if not _AV_OK:
            raise AudioBridgeError("aiortc / av 未安装")
        self._loop = loop
        self._sessions: Dict[str, _Session] = {}
        self._lock = threading.Lock()
        self._in_stream = None
        self._out_stream = None
        # 全局旋钮
        self._mic_muted = True         # 默认静音，避免开通话瞬间啸叫
        self._playback_volume = 0.6    # 0.0 ~ 1.0

    # ── 全局旋钮 ──
    def set_mic_muted(self, muted: bool):
        self._mic_muted = bool(muted)
        logger.info("麦克风 %s", "静音" if muted else "开启")

    def is_mic_muted(self) -> bool:
        return self._mic_muted

    def set_playback_volume(self, v: float):
        self._playback_volume = max(0.0, min(1.0, float(v)))

    def playback_volume(self) -> float:
        return self._playback_volume

    def active_count(self) -> int:
        with self._lock:
            return len(self._sessions)

    # ── 会话管理 ──
    def register_call(self, robot_id: str, conn) -> MicFanoutTrack:
        """给一台机器狗开通话：创建 track，加入 pc；订阅入站 frame；启动 sd 流。"""
        with self._lock:
            if robot_id in self._sessions:
                logger.warning("register_call: %s 已在通话中，忽略", robot_id)
                return self._sessions[robot_id].track

            track = MicFanoutTrack(self._loop)
            playback_buf = _RingBuffer()

            try:
                sender = conn.pc.addTrack(track)
            except Exception as e:
                track.close()
                raise AudioBridgeError(f"addTrack 失败：{e}")

            # 订阅入站音频帧
            async def _cb(frame, _rid=robot_id):
                self._on_robot_frame(_rid, frame)
            try:
                conn.audio.add_track_callback(_cb)
                conn.audio.switchAudioChannel(True)
            except Exception as e:
                # 尽力回滚 track
                try:
                    conn.pc.removeTrack(sender)
                except Exception:
                    pass
                track.close()
                raise AudioBridgeError(f"启动机器人音频通道失败：{e}")

            self._sessions[robot_id] = _Session(track, playback_buf, sender, conn)
            need_open = len(self._sessions) == 1

        if need_open:
            self._open_streams()

        logger.info("register_call OK：robot_id=%s，当前活动数=%d",
                    robot_id, self.active_count())
        return track

    def unregister_call(self, robot_id: str):
        with self._lock:
            sess = self._sessions.pop(robot_id, None)
            need_close = (not self._sessions) and (self._in_stream or self._out_stream)

        if sess is None:
            return

        try:
            sess.conn.audio.switchAudioChannel(False)
        except Exception as e:
            logger.debug("switchAudioChannel(False) 失败 [%s]：%s", robot_id, e)
        try:
            # 移除 track，避免 pc 关闭前还在扇出静音
            sess.conn.pc.removeTrack(sess.sender)
        except Exception as e:
            logger.debug("removeTrack 失败 [%s]：%s", robot_id, e)
        try:
            sess.track.close()
        except Exception:
            pass

        logger.info("unregister_call：robot_id=%s，剩余活动=%d",
                    robot_id, self.active_count())
        if need_close:
            self._close_streams()

    def shutdown(self):
        """整体关闭（App 退出时调用）。"""
        with self._lock:
            ids = list(self._sessions.keys())
        for rid in ids:
            try:
                self.unregister_call(rid)
            except Exception:
                pass
        self._close_streams()

    # ── sounddevice 流启停 ──
    def _open_streams(self):
        assert _SD_OK
        try:
            self._in_stream = _sd.InputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=SAMPLES_PER_FRAME, callback=self._mic_callback,
            )
            self._in_stream.start()
            logger.info("麦克风流已开启：%d Hz, %d ch", SAMPLE_RATE, CHANNELS)
        except Exception as e:
            logger.error("打开麦克风失败：%s", e)
            self._in_stream = None
            # 麦克风失败不影响接收：继续尝试打开扬声器
        try:
            self._out_stream = _sd.OutputStream(
                samplerate=SAMPLE_RATE, channels=CHANNELS, dtype="int16",
                blocksize=SAMPLES_PER_FRAME, callback=self._speaker_callback,
            )
            self._out_stream.start()
            logger.info("扬声器流已开启：%d Hz, %d ch", SAMPLE_RATE, CHANNELS)
        except Exception as e:
            logger.error("打开扬声器失败：%s", e)
            self._out_stream = None

    def _close_streams(self):
        for name in ("_in_stream", "_out_stream"):
            s = getattr(self, name)
            if s is None:
                continue
            try:
                s.stop(); s.close()
            except Exception as e:
                logger.debug("关闭 %s 异常：%s", name, e)
            setattr(self, name, None)
        logger.info("音频流已全部关闭")

    # ── sd 回调（audio thread）──
    def _mic_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("mic status: %s", status)
        # 静音：发零帧到所有 track，保持流活跃
        chunk = indata.copy()
        if self._mic_muted:
            chunk[:] = 0
        # 扇出（读锁保护 sessions 快照）
        with self._lock:
            tracks = [s.track for s in self._sessions.values()]
        for t in tracks:
            t.push(chunk)

    def _speaker_callback(self, outdata, frames, time_info, status):
        if status:
            logger.debug("speaker status: %s", status)
        # 收集所有活动 session 的 playback buffer
        with self._lock:
            bufs = [s.playback_buf for s in self._sessions.values()]

        if not bufs:
            outdata.fill(0)
            return

        # 简单求和混音，int32 中间量避免溢出，再 clip 回 int16
        mix = np.zeros((frames, CHANNELS), dtype=np.int32)
        for b in bufs:
            mix += b.read(frames).astype(np.int32)
        # 应用全局音量（乘完再 clip）
        v = self._playback_volume
        if v != 1.0:
            mix = (mix.astype(np.float32) * v).astype(np.int32)
        np.clip(mix, -32768, 32767, out=mix)
        outdata[:] = mix.astype(np.int16)

    # ── 入站帧处理（asyncio 线程）──
    def _on_robot_frame(self, robot_id: str, frame):
        # frame: av.AudioFrame
        try:
            arr = frame.to_ndarray()  # 形状可能 (channels, samples) 或 (1, samples*channels)
        except Exception as e:
            logger.debug("frame.to_ndarray 失败：%s", e)
            return

        # 归一到 (samples, channels) int16
        if arr.ndim == 1:
            arr = arr.reshape(-1, 1)
            arr = np.repeat(arr, CHANNELS, axis=1) if CHANNELS == 2 else arr
        elif arr.ndim == 2:
            if arr.shape[0] in (1, 2) and arr.shape[1] > arr.shape[0]:
                # planar or interleaved packed with (channels, samples)
                if arr.shape[0] == 1:
                    # packed 单行：可能是 samples*channels 交织
                    total = arr.shape[1]
                    if total % CHANNELS == 0:
                        arr = arr.reshape(-1, CHANNELS)
                    else:
                        arr = arr.reshape(-1, 1)
                        if CHANNELS == 2:
                            arr = np.repeat(arr, 2, axis=1)
                else:
                    # planar (channels, samples) -> 转置
                    arr = arr.T
            # else 已经是 (samples, channels)

        if arr.dtype != np.int16:
            # 有的情况会是 float32，转 int16
            arr = np.clip(arr, -32768, 32767).astype(np.int16) if arr.dtype in (np.int32,) \
                else (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16)

        # 采样率不匹配时理论上要重采样；aiortc 一般给 48k stereo，先不做重采样，
        # 万一遇到 8k/16k 单声道会有杂音，后续按需加 resampy。

        with self._lock:
            sess = self._sessions.get(robot_id)
        if sess is None:
            return
        sess.playback_buf.write(arr)
