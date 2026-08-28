#!/usr/bin/env python3
"""Open a web page on the person's screen.

    python3 open_url.py https://youtube.com
    python3 open_url.py youtube.com          # https:// is assumed

This exists so Lugalay can be given ONE precise permission instead of shell
access. A voice session cannot show an approval prompt, so anything not
pre-allowed simply fails — and the alternative to this script was allowing
`open` or `xdg-open` outright, which would let any binary on the machine be
launched by anything that can talk to the brain.

Only http and https are accepted. file://, javascript: and shell metacharacters
never reach a command line, because no shell is involved: the URL is passed as
a single argument.
"""
import re, subprocess, sys, urllib.parse

ALLOWED = ("http", "https")
# a hostname and nothing else: letters, digits, dots, hyphens, optional :port.
# Anything with a space, a semicolon or a colon-scheme in it is not a host.
HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d{1,5})?$")


def normalise(raw):
    """Return a safe http(s) URL, or None with a reason."""
    raw = (raw or "").strip()
    if not raw:
        return None, "no address given"
    if "://" not in raw:
        # bare "youtube.com" or "youtube.com/feed" — assume https, but only if
        # what comes before the first slash really is a hostname
        host = raw.split("/", 1)[0]
        if not HOST.match(host):
            return None, f"{raw!r} is not a web address"
        raw = "https://" + raw
    u = urllib.parse.urlparse(raw)
    if u.scheme not in ALLOWED:
        return None, f"{u.scheme!r} is not a web address — only http and https"
    if not u.netloc or not HOST.match(u.netloc):
        return None, "that is not a complete web address"
    return urllib.parse.urlunparse(u), None


def open_url(url):
    """Hand the URL to whatever this platform uses to open one."""
    if sys.platform == "darwin":
        cmd = ["open", url]
    elif sys.platform == "win32":
        # the empty string is start's window-title argument; without it a
        # quoted URL is taken as the title and nothing opens
        cmd = ["cmd", "/c", "start", "", url]
    else:
        cmd = ["xdg-open", url]
    # no shell=True: the URL stays one argument and is never parsed as a command
    subprocess.run(cmd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    url, err = normalise(" ".join(sys.argv[1:]))
    if err:
        print(err, file=sys.stderr)
        return 1
    try:
        open_url(url)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"could not open it: {e}", file=sys.stderr)
        return 1
    print(f"opened {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
