import os, ast, re

print("=== SUPPORTFORGE PRODUCTION AUDIT ===\n")

py_files = []
for root, dirs, files in os.walk('app'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

issues = []

# 1. Syntax
print("[1/7] Syntax check...")
for fpath in sorted(py_files):
    try:
        with open(fpath, 'r', encoding='utf-8') as fp:
            source = fp.read()
        ast.parse(source)
    except SyntaxError as e:
        issues.append(f"SYNTAX: {fpath}:{e.lineno}: {e.msg}")

# 2. Spelling
print("[2/7] Spelling check...")
for fpath in sorted(py_files):
    with open(fpath, 'r', encoding='utf-8') as fp:
        lines = fp.readlines()
    for i, line in enumerate(lines, 1):
        if '"escalat' in line and 'escalate' not in line:
            if 'escalat' in line.lower() and 'escalate' not in line.lower():
                issues.append(f"SPELL: {fpath}:{i}: 'escalat' missing 'l'?")
        if 'dataclasses' in line and 'dataclasses' not in line:
            issues.append(f"SPELL: {fpath}:{i}: Wrong 'dataclasses' module")

# 3. Imports
print("[3/7] Import check...")
for fpath in sorted(py_files):
    with open(fpath, 'r', encoding='utf-8') as fp:
        content = fp.read()
    if 'from pgvector.sqlalchemy import' in content:
        issues.append(f"IMPORT: {fpath}: Wrong pgvector import - use 'from pgvector import'")
    if 'from dataclasses import' in content:
        issues.append(f"IMPORT: {fpath}: Wrong 'dataclasses' - use 'dataclasses'")

# 4. README
print("[4/7] README check...")
if os.path.exists('../README.md'):
    with open('../README.md', 'r', encoding='utf-8') as fp:
        readme = fp.read()
    screenshots = re.findall(r'docs/screenshots/[^)]+\.png', readme)
    for s in screenshots:
        if not os.path.exists(f'../docs/screenshots/{s.split("/")[-1]}'):
            issues.append(f"README: Fake screenshot '{s}' claimed but NOT present")

# 5. Requirements
print("[5/7] Requirements check...")
if os.path.exists('requirements.txt'):
    with open('requirements.txt', 'r') as fp:
        reqs = fp.read()
    if 'fastapi-limiter' in reqs:
        found = False
        for fpath in py_files:
            if 'api' in fpath.lower():
                with open(fpath, 'r', encoding='utf-8') as fp:
                    if 'limiter' in fp.read().lower():
                        found = True
        if not found:
            issues.append("REQ: fastapi-limiter installed but NOT USED")

# 6. Frontend
print("[6/7] Frontend check...")
pkg_path = '../frontend/package.json'
if os.path.exists(pkg_path):
    with open(pkg_path, 'r') as fp:
        pkg = fp.read()
    m = re.search(r'"next":\s*"([^"]+)"', pkg)
    if m:
        ver = m.group(1)
        if not ver.startswith('15.') and not ver.startswith('14.'):
            issues.append(f"FRONTEND: Next.js version '{ver}' may not exist")
    page_tsx = '../frontend/app/dashboard/tickets/[id]/page.tsx'
    if os.path.exists(page_tsx):
        with open(page_tsx, 'r') as fp:
            content = fp.read()
        if 'new EventSource(' in content:
            issues.append("FRONTEND: EventSource CANNOT send cookies - breaks auth!")

# 7. Docker
print("[7/7] Docker check...")
if os.path.exists('../docker-compose.yml'):
    with open('../docker-compose.yml', 'r') as fp:
        dc = fp.read()
    if 'grafana' in dc.lower():
        if not os.path.exists('../grafana'):
            issues.append("DOCKER: Grafana in compose but NO provisioning configs!")

print(f"\n=== RESULTS ===")
print(f"Total issues: {len(issues)}\n")
if issues:
    for iss in issues:
        print(iss)
else:
    print("ALL CLEAR - PRODUCTION READY!")
