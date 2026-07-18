import os
import re
import urllib.request
from urllib.error import HTTPError, URLError

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

INPUT_FILE = "url.txt"
OUTPUT_FILE = "dnsmasq.txt"
TIMEOUT = 30

USER_AGENT = "Mozilla/5.0"

DOMAIN_REGEX = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)

ABP_SPLIT_REGEX = re.compile(r"[\^/$]")

DNSMASQ_REGEX = re.compile(
    r"^(?:address|local|server|ipset|nftset)=/([^/]+)/",
    re.IGNORECASE,
)

SKIP_DOMAINS = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "local",
}


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def extract_domain_from_line(line):
    line = line.rstrip("\r")
    line = line.split("#", 1)[0].strip().lower()

    if not line:
        return None

    # Ignore comments / ABP exceptions
    if line.startswith(("!", "@@")):
        return None

    # --------------------------------------------------------
    # dnsmasq
    # --------------------------------------------------------
    m = DNSMASQ_REGEX.match(line)
    if m:
        domain = m.group(1).strip(".")

        if domain in SKIP_DOMAINS:
            return None

        if DOMAIN_REGEX.fullmatch(domain):
            return domain

        return None

    # --------------------------------------------------------
    # Adblock Plus / AdGuard
    # --------------------------------------------------------
    if line.startswith("||"):
        line = line[2:]
        line = ABP_SPLIT_REGEX.split(line, 1)[0]

    # --------------------------------------------------------
    # Wildcards
    # --------------------------------------------------------
    if "*" in line:
        line = line.replace("*.", "")
        if "*" in line:
            return None

    parts = line.split()

    if not parts:
        return None

    # --------------------------------------------------------
    # Hosts files
    # --------------------------------------------------------
    if len(parts) >= 2:
        if parts[0] in (
            "0.0.0.0",
            "127.0.0.1",
            "::1",
            "::",
            "255.255.255.255",
        ):
            domain = parts[1]
        else:
            domain = parts[-1]
    else:
        domain = parts[0]

    domain = domain.strip(".")

    if domain in SKIP_DOMAINS:
        return None

    if not DOMAIN_REGEX.fullmatch(domain):
        return None

    return domain


# ------------------------------------------------------------
# Download blocklists
# ------------------------------------------------------------

def fetch_domains(url_file):
    if not os.path.exists(url_file):
        print(f"Missing: {url_file}")
        return set()

    with open(url_file, encoding="utf-8") as f:
        urls = [
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ]

    domains = set()

    total = len(urls)

    for index, url in enumerate(urls, 1):

        print(f"[{index}/{total}] Fetching: {url}")

        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                },
            )

            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:

                content = response.read().decode(
                    "utf-8",
                    errors="ignore",
                )

            added = 0

            for line in content.splitlines():

                domain = extract_domain_from_line(line)

                if domain and domain not in domains:
                    domains.add(domain)
                    added += 1

            print(f"    + {added:,} new domains")

        except (HTTPError, URLError) as e:
            print(f"    ERROR: {e}")

        except Exception as e:
            print(f"    ERROR: {e}")

    return domains


# ------------------------------------------------------------
# Remove redundant subdomains
# ------------------------------------------------------------

def filter_subdomains(domains):
    """
    Remove subdomains when parent domain exists.

    Example:

        ads.example.com
        img.example.com
        example.com

    becomes

        example.com
    """

    domain_set = domains
    kept = []

    for domain in domain_set:

        labels = domain.split(".")

        keep = True

        for i in range(1, len(labels)):

            parent = ".".join(labels[i:])

            if "." not in parent:
                break

            if parent in domain_set:
                keep = False
                break

        if keep:
            kept.append(domain)

    kept.sort()

    return kept


# ------------------------------------------------------------
# Output
# ------------------------------------------------------------

def write_dnsmasq(domains, filename):

    with open(filename, "w", encoding="utf-8") as f:

        f.writelines(
            f"address=/{domain}/0.0.0.0\n"
            for domain in domains
        )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    print("=" * 60)
    print("DNSMASQ Domain Aggregator")
    print("=" * 60)

    raw_domains = fetch_domains(INPUT_FILE)

    print()
    print(f"Downloaded unique domains : {len(raw_domains):,}")

    cleaned_domains = filter_subdomains(raw_domains)

    print(f"After subdomain removal   : {len(cleaned_domains):,}")
    print(f"Removed                   : {len(raw_domains) - len(cleaned_domains):,}")

    write_dnsmasq(cleaned_domains, OUTPUT_FILE)

    print()
    print(f"Successfully generated '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
