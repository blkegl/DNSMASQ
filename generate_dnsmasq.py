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

DOMAIN_REGEX = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)

SKIP_DOMAINS = {
    "localhost",
    "localhost.localdomain",
    "broadcasthost",
    "local",
}

USER_AGENT = "Mozilla/5.0"


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def extract_domain_from_line(line):
    line = line.split("#", 1)[0].strip().lower()

    if not line:
        return None

    if line.startswith(("!", "@@")):
        return None

    if line.startswith("||"):
        line = line[2:]
        line = re.split(r"[\^/$]", line, 1)[0]

    if "*" in line:
        line = line.replace("*.", "")
        if "*" in line:
            return None

    parts = line.split()

    if not parts:
        return None

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
# Download
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

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{total}] {url}")

        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT},
            )

            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                text = response.read().decode(
                    "utf-8",
                    errors="ignore",
                )

            added = 0
            for line in text.splitlines():
                domain = extract_domain_from_line(line)
                if domain and domain not in domains:
                    domains.add(domain)
                    added += 1

            print(f"    +{added:,}")

        except (HTTPError, URLError) as e:
            print(f"    ERROR: {e}")
        except Exception as e:
            print(f"    ERROR: {e}")

    return domains


# ------------------------------------------------------------
# Remove subdomains
# ------------------------------------------------------------

def filter_subdomains(domains):
    """
    Keep only the highest-level domain using fast O(1) set lookups.
    """
    domain_set = domains
    kept = []

    for domain in domain_set:
        labels = domain.split(".")
        keep = True

        for i in range(1, len(labels)):
            parent = ".".join(labels[i:])
            
            # Stop if the string left is just a root TLD framework (e.g. 'com', 'net')
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
        for domain in domains:
            f.write(f"address=/{domain}/0.0.0.0\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    print("=" * 60)
    print("DNSMASQ Domain Aggregator")
    print("=" * 60)

    raw = fetch_domains(INPUT_FILE)

    print()
    print(f"Downloaded unique domains : {len(raw):,}")

    filtered = filter_subdomains(raw)

    print(f"After subdomain removal   : {len(filtered):,}")
    print(f"Removed                   : {len(raw)-len(filtered):,}")

    write_dnsmasq(filtered, OUTPUT_FILE)

    print()
    print(f"Output written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()import os
import urllib.request
import re

def fetch_domains(url_file):
    if not os.path.exists(url_file):
        print(f"Error: {url_file} not found.")
        return set()

    domains = set()
    # Simple regex to validate basic domain structure
    domain_regex = re.compile(r'^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$', re.IGNORECASE)

    with open(url_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    for url in urls:
        try:
            print(f"Fetching: {url}")
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                content = response.read().decode('utf-8')
                for line in content.splitlines():
                    # Clean line: remove whitespace, comments, and common prefixes
                    cleaned = line.strip().lower()
                    if not cleaned or cleaned.startswith('#'):
                        continue
                    
                    # Handle hosts file format (e.g., "0.0.0.0 example.com")
                    parts = cleaned.split()
                    potential_domain = parts[-1] if parts else ""
                    
                    if domain_regex.match(potential_domain):
                        domains.add(potential_domain)
        except Exception as e:
            print(f"Failed to fetch {url}: {e}")
            
    return domains

def filter_subdomains(domains):
    """
    Removes redundant subdomains. If 'example.com' exists, 
    'sub.example.com' will be removed.
    """
    # Sort domains alphabetically by their reversed components
    # e.g., 'abc.example.com' -> ['com', 'example', 'abc']
    sorted_domains = sorted(domains, key=lambda d: d.split('.')[::-1])
    
    filtered = []
    for domain in sorted_domains:
        # Check if the current domain is a subdomain of the last added domain
        if filtered:
            last_domain = filtered[-1]
            if domain == last_domain or domain.endswith('.' + last_domain):
                continue  # Skip redundant subdomain
        filtered.append(domain)
        
    # Re-sort purely alphabetically for the final output
    return sorted(filtered)

def main():
    input_file = 'url.txt'
    output_file = 'dnsmasq.txt'
    
    print("Starting domain aggregation...")
    raw_domains = fetch_domains(input_file)
    print(f"Found {len(raw_domains)} unique raw domains.")
    
    cleaned_domains = filter_subdomains(raw_domains)
    print(f"Retained {len(cleaned_domains)} domains after subdomain filtering.")
    
    # Write to dnsmasq format: address=/domain.com/0.0.0.0
    # Change '0.0.0.0' to '#' or whatever fits your specific dnsmasq configuration needs
    with open(output_file, 'w') as f:
        for domain in cleaned_domains:
            f.write(f"local=/{domain}/\n")
            
    print(f"Successfully generated {output_file}")

if __name__ == '__main__':
    main()
