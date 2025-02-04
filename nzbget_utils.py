# Exit codes used by NZBGet
POSTPROCESS_SUCCESS = 93
POSTPROCESS_NONE = 95
POSTPROCESS_ERROR = 94


# Print with NZBGet log prefixes
def log_to_nzbget(msg, dest="DETAIL"):
    """
    Print each line of the input message with a prefix of [dest].

    Args:
        msg (str): The message to be logged, possibly containing multiple lines.
        dest (str): The log destination (e.g., DETAIL, INFO, WARNING, ERROR).
    """
    prefix = f"[{dest}] "
    for line in msg.splitlines():
        print(f"{prefix}{line}")


def logdet(msg):
    return log_to_nzbget(msg, "DETAIL")


def loginf(msg):
    return log_to_nzbget(msg, "INFO")


def logwar(msg):
    return log_to_nzbget(msg, "WARNING")


def logerr(msg):
    return log_to_nzbget(msg, "ERROR")
