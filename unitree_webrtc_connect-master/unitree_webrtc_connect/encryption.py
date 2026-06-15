from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5
import base64
import uuid
import binascii
import logging as _logging

# EC key support (本地补丁：部分早期/边缘固件返回 EC 公钥而非 RSA)
try:
    from cryptography.hazmat.primitives.asymmetric.ec import (
        ECDH, generate_private_key, SECP256R1
    )
    from cryptography.hazmat.primitives.serialization import (
        load_der_public_key, Encoding, PublicFormat
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.hashes import SHA256
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM as _AESGCM
    _EC_AVAILABLE = True
except ImportError:
    _EC_AVAILABLE = False

###############
### AES handling
###############

# Function to generate a UUID and return it as a 32-character hexadecimal string
def _generate_uuid() -> str:
    uuid_32 = uuid.uuid4().bytes  
    uuid_32_hex_string = binascii.hexlify(uuid_32).decode('utf-8')
    return uuid_32_hex_string

def pad(data: str) -> bytes:
    """Pad data to be a multiple of 16 bytes (AES block size)."""
    block_size = AES.block_size
    padding = block_size - len(data) % block_size
    padded_data = data + chr(padding) * padding
    return padded_data.encode('utf-8')

def unpad(data: bytes) -> str:
    """Remove padding from data."""
    padding = data[-1]
    return data[:-padding].decode('utf-8')

def aes_encrypt(data: str, key: str) -> str:
    """Encrypt the given data using AES (ECB mode with PKCS5 padding)."""
    # Ensure key is 32 bytes for AES-256
    key_bytes = key.encode('utf-8')

    # Pad the data to ensure it is a multiple of block size
    padded_data = pad(data)

    # Create AES cipher in ECB mode
    cipher = AES.new(key_bytes, AES.MODE_ECB)

    # Encrypt data
    encrypted_data = cipher.encrypt(padded_data)

    # Encode encrypted data to Base64
    encoded_encrypted_data = base64.b64encode(encrypted_data).decode('utf-8')

    return encoded_encrypted_data

def aes_decrypt(encrypted_data: str, key: str) -> str:
    """Decrypt the given data using AES (ECB mode with PKCS5 padding)."""
    # Ensure key is 32 bytes for AES-256
    key_bytes = key.encode('utf-8')

    # Decode Base64 encrypted data
    encrypted_data_bytes = base64.b64decode(encrypted_data)

    # Create AES cipher in ECB mode
    cipher = AES.new(key_bytes, AES.MODE_ECB)

    # Decrypt data
    decrypted_padded_data = cipher.decrypt(encrypted_data_bytes)

    # Unpad the decrypted data
    decrypted_data = unpad(decrypted_padded_data)

    return decrypted_data

# Function to generate an AES key
def generate_aes_key() -> str:
    return _generate_uuid()

###############
### RSA handling
###############

def _try_load_ec_public_key(pem_data: str):
    """Try to load an EC public key. Returns cryptography EC key object or None."""
    if not _EC_AVAILABLE:
        return None
    try:
        key_bytes = base64.b64decode(pem_data)
        if len(key_bytes) == 65 and key_bytes[0] == 0x04:
            spki_prefix = bytes([
                0x30, 0x59,
                0x30, 0x13,
                0x06, 0x07, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x02, 0x01,
                0x06, 0x08, 0x2a, 0x86, 0x48, 0xce, 0x3d, 0x03, 0x01, 0x07,
                0x03, 0x42, 0x00,
            ])
            spki_der = spki_prefix + key_bytes
            ec_key = load_der_public_key(spki_der, backend=default_backend())
            _logging.info("_try_load_ec_public_key: 成功加载未压缩 EC 点 (65 bytes)")
            return ec_key
        ec_key = load_der_public_key(key_bytes, backend=default_backend())
        _logging.info("_try_load_ec_public_key: 成功加载 SubjectPublicKeyInfo DER")
        return ec_key
    except Exception as e:
        _logging.debug("_try_load_ec_public_key: DER 失败 (%s)", e)

    try:
        cleaned = pem_data.strip().replace("\n", "").replace("\r", "")
        pem_wrapped = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(cleaned[i:i+64] for i in range(0, len(cleaned), 64))
            + "\n-----END PUBLIC KEY-----\n"
        )
        from cryptography.hazmat.primitives.serialization import load_pem_public_key
        ec_key = load_pem_public_key(pem_wrapped.encode(), backend=default_backend())
        _logging.info("_try_load_ec_public_key: 成功加载 PEM 包装 EC 公钥")
        return ec_key
    except Exception as e:
        _logging.debug("_try_load_ec_public_key: PEM 包装失败 (%s)", e)

    return None


def rsa_load_public_key(pem_data: str):
    """Load a public key. RSA 优先，失败回退到 EC。返回 RSA 或 EC 公钥对象。"""
    # 方式 1：原始 base64 DER → RSA
    try:
        key_bytes = base64.b64decode(pem_data)
        return RSA.import_key(key_bytes)
    except Exception as e1:
        _logging.debug("rsa_load_public_key: DER RSA 失败 (%s)", e1)

    # 方式 2：PEM 包装后再 import RSA
    try:
        cleaned = pem_data.strip().replace("\n", "").replace("\r", "")
        pem_wrapped = (
            "-----BEGIN PUBLIC KEY-----\n"
            + "\n".join(cleaned[i:i+64] for i in range(0, len(cleaned), 64))
            + "\n-----END PUBLIC KEY-----"
        )
        return RSA.import_key(pem_wrapped)
    except Exception as e2:
        _logging.debug("rsa_load_public_key: PEM RSA 包装失败 (%s)", e2)

    # 方式 3：直接当 PEM 字符串导入 RSA
    try:
        return RSA.import_key(pem_data)
    except Exception as e3:
        _logging.debug("rsa_load_public_key: 直接 PEM RSA 失败 (%s)", e3)

    # 方式 4：EC 兜底
    ec_key = _try_load_ec_public_key(pem_data)
    if ec_key is not None:
        return ec_key

    _logging.error("rsa_load_public_key: 所有格式均失败。key 前 80 字符: %r", pem_data[:80])
    raise ValueError("公钥格式不受支持 (RSA/EC 均失败)")


def rsa_encrypt(data: str, public_key) -> str:
    """Encrypt data with RSA (PKCS1v1.5) or EC (ECIES = ECDH + HKDF-SHA256 + AES-256-GCM)."""
    if _EC_AVAILABLE:
        from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
        if isinstance(public_key, EllipticCurvePublicKey):
            return _ec_encrypt(data, public_key)

    cipher = PKCS1_v1_5.new(public_key)
    max_chunk_size = public_key.size_in_bytes() - 11
    data_bytes = data.encode('utf-8')

    encrypted_bytes = bytearray()
    for i in range(0, len(data_bytes), max_chunk_size):
        chunk = data_bytes[i:i + max_chunk_size]
        encrypted_chunk = cipher.encrypt(chunk)
        encrypted_bytes.extend(encrypted_chunk)

    encoded_encrypted_data = base64.b64encode(encrypted_bytes).decode('utf-8')
    return encoded_encrypted_data


def _ec_encrypt(data: str, peer_public_key) -> str:
    """ECIES: ephemeral_pub(65) || nonce(12) || ciphertext+tag, base64."""
    import os
    ephemeral_private = generate_private_key(SECP256R1(), default_backend())
    ephemeral_public = ephemeral_private.public_key()

    shared_secret = ephemeral_private.exchange(ECDH(), peer_public_key)

    hkdf = HKDF(algorithm=SHA256(), length=32, salt=None, info=b'', backend=default_backend())
    aes_key = hkdf.derive(shared_secret)

    nonce = os.urandom(12)
    aesgcm = _AESGCM(aes_key)
    plaintext = data.encode('utf-8')
    ciphertext_tag = aesgcm.encrypt(nonce, plaintext, None)

    ephemeral_pub_bytes = ephemeral_public.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    result = ephemeral_pub_bytes + nonce + ciphertext_tag
    _logging.info("_ec_encrypt: ECIES 加密完成, 输出长度=%d bytes", len(result))
    return base64.b64encode(result).decode('utf-8')

# Example usage
if __name__ == "__main__":
    # Public key
    public_key_pem = """
    MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnOc1sgpzL4GTVp9/oQ0H
    D7eeAO2GJUABfjX3TitgXiXN1Ktn2WLsLrtAiIuj3OrrRogx8fCT16oxnXx/Xrap
    BRHD/ufHZ08A2IRVw6U6vKDv8TpQH22sAEtUji4/P2AaZmeOxFsYW5FshQr37KBG
    +cBb7rJWLWEJpIXmCpnt37GGCtsACqRegkl7qQ8Q0OiJmtrYLPi00xSstZb+Wv1v
    8B0eTY3POAUXjgl357L5dc6vS99rYFkYeUCTWHaH4d51Z/KgCRYUadboDc2cgNg/
    z2dbO9S3HADegbIsN3fTbjDCruKfvc5ejxlFZ0Xbu6SScQbmkP8t3TPvy/DXGJAh
    NwIDAQAB
    """

    # Example value of UUID or data you wish to encrypt
    value_of = "26a663562a6f4dfbbbbf2b50c1a278cb"

    # Load public key
    public_key = rsa_load_public_key(public_key_pem)

    # Encrypt the message
    encrypted_value = rsa_encrypt(value_of, public_key)
    print(f"Encrypted Value: {encrypted_value}")

    # AES testing
    aes_key = "26a663562a6f4dfbbbbf2b50c1a278cb"  # Example 32-character UUID

    # Encrypt a message with AES
    encrypted_message = aes_encrypt("Hello, world!", aes_key)
    print(f"Encrypted AES Message: {encrypted_message}")

    # Decrypt the AES message
    decrypted_message = aes_decrypt(encrypted_message, aes_key)
    print(f"Decrypted AES Message: {decrypted_message}")
