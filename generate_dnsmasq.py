import os
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
            f.write(f"address=/{domain}/0.0.0.0\n")
            
    print(f"Successfully generated {output_file}")

if __name__ == '__main__':
    main()
