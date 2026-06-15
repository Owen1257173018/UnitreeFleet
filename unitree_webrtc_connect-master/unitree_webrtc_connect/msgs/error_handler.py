from ..constants import app_error_messages
import time

def integer_to_hex_string(error_code):
    """
    Converts an integer error code to a hexadecimal string.
    
    Args:
        error_code (int): The error code as an integer.
        
    Returns:
        str: The error code as a hexadecimal string, without the '0x' prefix, in uppercase.
    """
    if not isinstance(error_code, int):
        raise ValueError("Input must be an integer.")

    # Convert the integer to a hex string and remove the '0x' prefix
    hex_string = hex(error_code)[2:].upper()

    return hex_string

def get_error_code_text(error_source, error_code):
    """
    Retrieve the error message based on the error source and error code.

    Args:
        error_code_dict (dict): Dictionary mapping error codes to messages.
        error_source (int): The error source code (e.g., 100, 200, etc.).
        error_code (str): The specific error code in string form (e.g., "01", "10").

    Returns:
        str: The corresponding error message, or the fallback format.
    """
    # Generate the key for looking up the error message
    key = f"app_error_code_{error_source}_{error_code}"
    
    # Check if the key exists in the error_code_dict
    if key in app_error_messages:
        return app_error_messages[key]
    else:
        # Fallback: return the combination of error_source and error_code
        return f"{error_source}-{error_code}"

def get_error_source_text(error_source):
    """
    Retrieve the error message based on the error source and error code.

    Args:
        error_code_dict (dict): Dictionary mapping error codes to messages.
        error_source (int): The error source code (e.g., 100, 200, etc.).
        error_code (str): The specific error code in string form (e.g., "01", "10").

    Returns:
        str: The corresponding error message, or the fallback format.
    """
    # Generate the key for looking up the error message
    key = f"app_error_source_{error_source}"
    
    # Check if the key exists in the error_code_dict
    if key in app_error_messages:
        return app_error_messages[key]
    else:
        # Fallback: return the combination of error_source and error_code
        return f"{error_source}"

def handle_error(message):
    """
    Handle an error data-channel message and print it.

    Three message types share this handler — confirmed against the Unitree app
    source (UnitreeGo APK):
      - "errors"    : data is a list of [ts, src, code] (full snapshot)
      - "add_error" : data is a single [ts, src, code] (one new error)
      - "rm_error"  : data is a single [ts, src, code] (one cleared error)
    Normalise the single-tuple cases to a list so one loop handles all three.

    Args:
        message (dict): The error message with `type` and `data` fields.
    """
    msg_type = message.get("type")
    data = message.get("data") or []
    if data and not isinstance(data[0], (list, tuple)):
        data = [data]

    icon = {"add_error": "🚨", "rm_error": "✅", "errors": "📋"}.get(msg_type, "🚨")
    verb = {"add_error": "appeared", "rm_error": "cleared", "errors": "active"}.get(msg_type, "received")

    for timestamp, error_source, error_code_int in data:
        readable_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(timestamp))
        error_source_text = get_error_source_text(error_source)
        error_code_hex = integer_to_hex_string(error_code_int)
        error_code_text = get_error_code_text(error_source, error_code_hex)

        print(f"\n{icon} Error {verb}:\n"
            f"🕒 Time:          {readable_time}\n"
            f"🔢 Error Source:  {error_source_text}\n"
            f"❗ Error Code:    {error_code_text}\n")
