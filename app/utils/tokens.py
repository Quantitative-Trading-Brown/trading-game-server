import random, binascii, secrets, string

def generate_code(length=6):
    """Generate a random alphanumeric game code."""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

def generate_token(prefix, length=32):
    """Generate a random token."""
    return prefix + binascii.hexlify(secrets.token_bytes(length)).decode("utf-8")

