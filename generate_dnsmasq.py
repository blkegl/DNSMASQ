import os
import re
import requests

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

INPUT_FILE = "url.txt"
# We will use this base name to generate dnsmasq1.txt, dnsmasq2.txt, etc.
OUTPUT_FILE_BASE = "dnsmasq" 
NUM_SPLIT_FILES = 10
TIMEOUT = 30

USER_AGENT = "Mozilla/5.0"

# Main domain validation regex (handles standard domains and punycode)
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
# Helpers
# ------------------------------------------------------------

def format_size(size_bytes):
    """Formats bytes into human-readable B, KB, or MB."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"


def is_valid_domain(domain):
    """Validates domain structure and handles IDNA (Punycode) translation."""
    if not domain or domain in SKIP_DOMAINS:
        return None
    try:
        # Convert IDN (e.g., bücher.de) to punycode (xn--bcher-kva.de)
        punycode = domain.encode("idna").decode("ascii")
        # Validate syntax against the precompiled regex
        if DOMAIN_REGEX.fullmatch(punycode):
            return punycode
    except Exception:
        pass
    return None


# ------------------------------------------------------------
# Parsing
# ------------------------------------------------------------

def extract_domain_from_line(line):
    line = line.rstrip("\r\n")
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
        return m.group(1).strip(".")

    # --------------------------------------------------------
    # Adblock Plus / AdGuard (handles ||example.com^, example.com^, example.com$)
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
        if parts[0] in ("0.0.0.0", "127.0.0.1", "::1", "::", "255.255.255.255"):
            domain = parts[1]
        else:
            domain = parts[-1]
    else:
        domain = parts[0]

    return domain.strip(".")


# ------------------------------------------------------------
# Download blocklists
# ------------------------------------------------------------

def fetch_domains(url_file):
    if not os.path.exists(url_file):
        print(f"Missing: {url_file}")
        return set(), [], 0, 0

    with open(url_file, encoding="utf-8") as f:
        # Deduplicate URLs while preserving declaration order
        urls = list(dict.fromkeys(
            line.strip()
            for line in f
            if line.strip() and not line.lstrip().startswith("#")
        ))

    global_domains = set()
    source_metrics = []
    global_raw_processed = 0
    successful_downloads = 0

    total = len(urls)

    # Context-managed session for proper socket cleanup
    with requests.Session() as session:
        session.headers.update({"User-Agent": USER_AGENT})

        for index, url in enumerate(urls, 1):
            print(f"[{index}/{total}] Fetching: {url}")

            try:
                with session.get(url, timeout=TIMEOUT, stream=True) as response:
                    response.raise_for_status()
                    
                    # Try getting content length from header
                    content_length = response.headers.get("Content-Length")
                    byte_size = int(content_length) if content_length and content_length.isdigit() else 0
                    
                    file_unique_domains = set()
                    file_raw_count = 0
                    fallback_byte_size = 0

                    # Stream raw bytes to ensure total compatibility across requests versions
                    for raw_line in response.iter_lines(decode_unicode=False):
                        if raw_line is None:
                            continue
                        
                        # Fallback parsing sizes manually if Content-Length header is omitted
                        if not byte_size:
                            fallback_byte_size += len(raw_line) + 1 
                        
                        line = raw_line.decode("utf-8", errors="ignore")
                        extracted = extract_domain_from_line(line)
                        
                        if extracted:
                            file_raw_count += 1
                            
                            validated = is_valid_domain(extracted)
                            if validated:
                                file_unique_domains.add(validated)
                                global_domains.add(validated)

                global_raw_processed += file_raw_count
                successful_downloads += 1
                final_bytes = byte_size if byte_size else fallback_byte_size

                source_metrics.append({
                    "url": url,
                    "bytes": final_bytes,
                    "unique_domains": len(file_unique_domains)
                })

                print(f"    + {len(file_unique_domains):,} unique valid domains found")

            except requests.exceptions.RequestException as e:
                print(f"    ERROR: {e}")
            except Exception as e:
                print(f"    ERROR: {e}")

    # Sort source metrics descending based on unique domain counts
    source_metrics.sort(key=lambda x: x["unique_domains"], reverse=True)

    return global_domains, source_metrics, global_raw_processed, successful_downloads


# ------------------------------------------------------------
# Remove redundant subdomains
# ------------------------------------------------------------

def filter_subdomains(domains):
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
# Output Splitting Logic
# ------------------------------------------------------------

def write_split_dnsmasq(domains, base_filename, num_splits=10):
    """Splits domains uniformly across a specified number of files."""
    total_domains = len(domains)
    if total_domains == 0:
        print("[WARNING] No domains to write.")
        return

    # Determine standard chunk sizing and handle mathematical remainders smoothly
    avg_chunk = total_domains // num_splits
    remainder = total_domains % num_splits

    start_idx = 0
    for i in range(1, num_splits + 1):
        # Dynamically distribute the remainder across the first few chunks
        chunk_size = avg_chunk + (1 if i <= remainder else 0)
        end_idx = start_idx + chunk_size
        
        chunk_domains = domains[start_idx:end_idx]
        filename = f"{base_filename}{i}.txt"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.writelines(f"address=/{domain}/\n" for domain in chunk_domains)
            
        print(f"    └─ Written {len(chunk_domains):,} domains to {filename}")
        start_idx = end_idx


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():
    raw_domains, source_metrics, global_raw_processed, total_sources = fetch_domains(INPUT_FILE)
    
    cleaned_domains = filter_subdomains(raw_domains)
    
    print("\n" + "=" * 50)
    print(f" WRITING SPLIT OUTPUTS ({NUM_SPLIT_FILES} Files)")
    print("=" * 50)
    write_split_dnsmasq(cleaned_domains, OUTPUT_FILE_BASE, NUM_SPLIT_FILES)

    print("\n" + "=" * 50)
    print(" INDIVIDUAL SOURCE METRICS REPORT")
    print("=" * 50)
    for metric in source_metrics:
        print(f"Source: {metric['url']}")
        print(f"  └─ File Size: {format_size(metric['bytes'])}")
        print(f"  └─ Unique Valid Domains: {metric['unique_domains']:,}\n")

    global_unique = len(raw_domains)
    global_removed = global_raw_processed - global_unique
    after_subdomain_removal = len(cleaned_domains)
    subdomains_removed = global_unique - after_subdomain_removal

    print("=" * 50)
    print(f"[INFO] Downloaded sources: {total_sources}")
    print(f"[INFO] Raw domains processed: {global_raw_processed:,}")
    print(f"[INFO] Global unique valid domains: {global_unique:,}")
    print(f"[INFO] Global duplicates/invalid removed: {global_removed:,}")
    print(f"[INFO] After subdomain removal: {after_subdomain_removal:,}")
    print(f"[INFO] Subdomains removed: {subdomains_removed:,}")
    print("=" * 50)


if __name__ == "__main__":
    main()
