import os
import re
import sys

def parse_markdown(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    headings = []
    code_blocks = []
    links = []

    # Simple parser
    in_code_block = False
    code_block_lang = ""
    for line_num, line in enumerate(lines, 1):
        # Code block tracking
        if line.strip().startswith('```'):
            if not in_code_block:
                in_code_block = True
                code_block_lang = line.strip()[3:].strip()
                code_blocks.append((line_num, code_block_lang))
            else:
                in_code_block = False
            continue

        if in_code_block:
            continue

        # Heading tracking
        heading_match = re.match(r'^(#{1,6})\s+(.*)$', line)
        if heading_match:
            headings.append((line_num, len(heading_match.group(1)), heading_match.group(2).strip()))

        # Link tracking
        # Find all markdown links [text](url)
        link_matches = re.findall(r'\[([^\]]+)\]\(([^)]+)\)', line)
        for text, url in link_matches:
            links.append((line_num, text.strip(), url.strip()))

    return headings, code_blocks, links

def verify_parity(en_path, vi_path):
    en_headings, en_code_blocks, en_links = parse_markdown(en_path)
    vi_headings, vi_code_blocks, vi_links = parse_markdown(vi_path)

    errors = []

    # Verify headings structure
    if len(en_headings) != len(vi_headings):
        errors.append(f"Heading count mismatch: EN has {len(en_headings)}, VI has {len(vi_headings)}")
    else:
        for i, (en_h, vi_h) in enumerate(zip(en_headings, vi_headings)):
            if en_h[1] != vi_h[1]:
                errors.append(f"Heading level mismatch at index {i}: EN level {en_h[1]} ('{en_h[2]}') vs VI level {vi_h[1]} ('{vi_h[2]}')")

    # Verify code blocks structure
    if len(en_code_blocks) != len(vi_code_blocks):
        errors.append(f"Code block count mismatch: EN has {len(en_code_blocks)}, VI has {len(vi_code_blocks)}")
    else:
        for i, (en_cb, vi_cb) in enumerate(zip(en_code_blocks, vi_code_blocks)):
            # Check language identifier
            en_lang = en_cb[1].split()[0] if en_cb[1] else ""
            vi_lang = vi_cb[1].split()[0] if vi_cb[1] else ""
            if en_lang != vi_lang:
                errors.append(f"Code block language mismatch at index {i}: EN language '{en_cb[1]}' (line {en_cb[0]}) vs VI language '{vi_cb[1]}' (line {vi_cb[0]})")

    # Verify links
    # Note: Link text might be translated, but the URLs should generally match or point to translated equivalents
    # For simplicity, we check if the link counts match and if the URLs match for cross-links
    if len(en_links) != len(vi_links):
        errors.append(f"Link count mismatch: EN has {len(en_links)}, VI has {len(vi_links)}")
    else:
        for i, (en_link, vi_link) in enumerate(zip(en_links, vi_links)):
            en_url = en_link[2]
            vi_url = vi_link[2]
            # Normalize URLs for comparison (e.g. 02_infra_design.md vs 02_infra_design_vi.md)
            en_norm = re.sub(r'\.md$', '', en_url)
            vi_norm = re.sub(r'_vi\.md$', '', vi_url).replace('_vi', '') # remove _vi if any
            if en_norm != vi_norm and not (en_url.startswith('http') or en_url.startswith('#')):
                errors.append(f"Link target mismatch at index {i}: EN points to '{en_url}' (line {en_link[0]}) vs VI points to '{vi_url}' (line {vi_link[0]})")

    return errors

def main():
    docs_dir = os.path.join("docs", "tf2-finops")
    files = sorted(os.listdir(docs_dir))
    
    en_files = [f for f in files if f.endswith(".md") and not f.endswith("_vi.md") and f != "NOTES.md" and f != "AWS_Component_details.md"]
    
    all_passed = True
    print("Starting document parity verification...")
    print("=" * 60)
    
    for en_file in en_files:
        vi_file = en_file.replace(".md", "_vi.md")
        en_path = os.path.join(docs_dir, en_file)
        vi_path = os.path.join(docs_dir, vi_file)
        
        if not os.path.exists(vi_path):
            print(f"[WARNING] Vietnamese version for {en_file} is missing.")
            continue
            
        print(f"Comparing {en_file} <-> {vi_file}...", end=" ")
        errors = verify_parity(en_path, vi_path)
        
        if errors:
            print("FAILED")
            all_passed = False
            for err in errors:
                print(f"  - {err}")
        else:
            print("PASSED")
            
    print("=" * 60)
    if all_passed:
        print("All documents passed parity verification successfully!")
        sys.exit(0)
    else:
        print("Some documents failed parity verification. Please fix them.")
        sys.exit(1)

if __name__ == "__main__":
    main()
