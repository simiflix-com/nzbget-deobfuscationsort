# Exit codes used by NZBGet
POSTPROCESS_SUCCESS = 93
POSTPROCESS_NONE = 95
POSTPROCESS_ERROR = 94


# Print with NZBGet log prefixes
def log_to_nzbget(msg, dest="DETAIL"):
    print(f"[{dest}] {msg}")


def logdet(msg):
    return log_to_nzbget(msg, "DETAIL")


def loginf(msg):
    return log_to_nzbget(msg, "INFO")


def logwar(msg):
    return log_to_nzbget(msg, "WARNING")


def logerr(msg):
    return log_to_nzbget(msg, "ERROR")
