import json
import logging
import random
import time

from Crypto.PublicKey import RSA

from .encryption import (
    aes_decrypt,
    generate_aes_key,
    rsa_encrypt,
    rsa_load_public_key,
)
from .unitree_cloud import UnitreeCloud, UnitreeCloudError


def generate_uuid():
    def replace_char(char):
        rand = random.randint(0, 15)
        if char == "x":
            return format(rand, "x")
        elif char == "y":
            return format((rand & 0x3) | 0x8, "x")

    uuid_template = "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx"
    return "".join(replace_char(c) if c in "xy" else c for c in uuid_template)


def get_nested_field(message, *fields):
    current_level = message
    for field in fields:
        if isinstance(current_level, dict) and field in current_level:
            current_level = current_level[field]
        else:
            return None
    return current_level


# ─── Cloud-backed helpers used by the Remote (STA-T) signaling flow ───

def fetch_token(email: str, password: str, region: str = "global",
                device_type: str = "Go2") -> str:
    """Login to the Unitree cloud and return the access token."""
    logging.info("Obtaining TOKEN...")
    try:
        cloud = UnitreeCloud(region=region, device_type=device_type)
        return cloud.login_email(email, password)
    except UnitreeCloudError as e:
        logging.error(str(e))
        return None


def fetch_public_key(region: str = "global", device_type: str = "Go2") -> RSA.RsaKey:
    """Fetch the cloud's RSA public key for wrapping session AES keys."""
    logging.info("Obtaining a Public key...")
    try:
        cloud = UnitreeCloud(region=region, device_type=device_type)
        pem = cloud.get_pub_key()
        if not pem:
            return None
        return rsa_load_public_key(pem)
    except (UnitreeCloudError, Exception) as e:
        logging.error(f"Failed to fetch public key: {e}")
        return None


def fetch_turn_server_info(serial: str, access_token: str,
                           public_key: RSA.RsaKey, region: str = "global",
                           device_type: str = "Go2") -> dict:
    """Fetch TURN credentials for the Remote signaling flow."""
    logging.info("Obtaining TURN server info...")
    aes_key = generate_aes_key()
    try:
        cloud = UnitreeCloud(
            region=region, device_type=device_type, access_token=access_token,
        )
        encrypted = cloud.webrtc_account(serial, rsa_encrypt(aes_key, public_key))
        if not encrypted:
            return None
        return json.loads(aes_decrypt(encrypted, aes_key))
    except (UnitreeCloudError, Exception) as e:
        logging.error(f"Failed to fetch TURN server info: {e}")
        return None


def print_status(status_type, status_message):
    current_time = time.strftime("%H:%M:%S")
    print(f"🕒 {status_type:<25}: {status_message:<15} ({current_time})")
