"""
Complete audit of ALL files in SupportForge backend.
Checks: syntax, imports, spelling, logic bugs, missing implementations.
"""
import ast
import os
import re
import sys

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

issues = []
warnings = []
passed = []

def log_issue(file, line, msg):
    issues.append(f"{RED}[BUG] {file}:{line}: {msg}{RESET}")

def log_warn(file, line, msg):
    warnings.append(f"{YELLOW}[WARN] {file}:{line}: {msg}{RESET}")

def log_pass(msg):
    passed.append(f"{GREEN}[OK] {msg}{RESET}")

print(f"{BLUE}{'='*60}{RESET}")
print(f"{BLUE}SUPPORTFORGE COMPLETE AUDIT{RESET}")
print(f"{BLUE}{'='*60}{RESET}")

# ========== 1. SYNTAX CHECK ALL PYTHON FILES ==========
print(f"\n{BLUE}[1/10] SYNTAX CHECK{RESET}")
py_files = []
for root, dirs, files in os.walk('app'):
    dirs[:] = [d for d in dirs if d != '__pycache__']
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

syntax_errors = 0
for fpath in sorted(py_files):
    try:
        with open(fpath, 'r', encoding='utf-8') as fp:
            source = fp.read()
        ast.parse(source)
        log_pass(f"Syntax: {fpath}")
    except SyntaxError as e:
        log_issue(fpath, e.lineno or 0, f"SyntaxError: {e.msg}")
        syntax_errors += 1

# ========== 2. SPELLING CHECKS ==========
print(f"\n{BLUE}[2/10] SPELLING CHECK{RESET}")
spelling_bugs = 0
for fpath in sorted(py_files):
    with open(fpath, 'r', encoding='utf-8') as fp:
        lines = fp.readlines()
    for i, line in enumerate(lines, 1):
        # Check "escalate" missing 'l'
        if 'escalat' in line.lower() and 'escalate' not in line.lower():
            if 'escalat' in line.lower():
                log_issue(fpath, i, f"Spelling: 'escalat' should be 'escalate' -> {line.strip()}")
                spelling_bugs += 1
        # Check dataclasses vs dataclasses
        if 'dataclasses' in line and 'dataclasses' not in line:
            log_issue(fpath, i, f"Import: 'dataclasses' module does not exist, should be 'dataclasses'")
            spelling_bugs += 1
        # Check pgvector vs pgvector
        if 'pgvector' in line and 'pgvector' not in line:
            log_issue(fpath, i, f"Import: 'pgvector' module may not exist, should be 'pgvector'")
            spelling_bugs += 1

# ========== 3. CHECK README CLAIMS ==========
print(f"\n{BLUE}[3/10] README CLAIMS CHECK{RESET}")
readme_path = '../README.md'
if os.path.exists(readme_path):
    with open(readme_path, 'r', encoding='utf-8') as fp:
        readme = fp.read()

    # Check screenshot claims
    screenshot_claims = re.findall(r'docs/screenshots/(\S+\.png)', readme)
    for s in screenshot_claims:
        if not os.path.exists(f'../docs/screenshots/{s}'):
            log_issue('../README.md', 0, f"FAKE SCREENSHOT: docs/screenshots/{s} does not exist")

    # Check duplicate invariants
    invariant_lines = [l for l in readme.split('\n') if 'Invariant' in l or 'invariant' in l]
    log_pass(f"README: {len(invariant_lines)} invariant mentions found")

    # Check 21 invariants claim
    if '21 enforced invariants' in readme:
        # Count actual unique invariants
        inv_list = re.findall(r'\|\s*(\d+)\s*\|', readme)
        if inv_list:
            unique_invs = set(int(i) for i in inv_list)
            if len(unique_invs) < 21:
                log_warn('../README.md', 0, f"Claim 21 invariants but only {len(unique_invs)} unique numbers found")
else:
    log_warn('..', 0, "README.md not found")

# ========== 4. CHECK FRONTEND ==========
print(f"\n{BLUE}[4/10] FRONTEND CHECK{RESET}")
# Check package.json version
pkg_path = '../frontend/package.json'
if os.path.exists(pkg_path):
    with open(pkg_path, 'r') as fp:
        pkg = fp.read()
    # Check next version
    next_match = re.search(r'"next":\s*"([^"]+)"', pkg)
    if next_match:
        ver = next_match.group(1)
        if not ver.startswith('15.') and not ver.startswith('14.'):
            log_warn(pkg_path, 0, f"Next.js version '{ver}' may not exist, use 15.x")
    # Check EventSource usage
    page_tsx = '../frontend/app/dashboard/tickets/[id]/page.tsx'
    if os.path.exists(page_tsx):
        with open(page_tsx, 'r') as fp:
            content = fp.read()
        if 'new EventSource(' in content:
            log_issue(page_tsx, 0, "EventSource CANNOT send cookies - breaks authenticated SSE streaming")
else:
    log_warn('..', 0, "frontend/package.json not found")

# ========== 5. CHECK DOCKER COMPOSE ==========
print(f"\n{BLUE}[5/10] DOCKER CHECK{RESET}")
dc_path = '../docker-compose.yml'
if os.path.exists(dc_path):
    with open(dc_path, 'r') as fp:
        dc = fp.read()
    if 'libretranslate' in dc and 'translate' not in open('../backend/app/agents/resolver.py').read().lower():
        log_warn(dc_path, 0, "LibreTranslate in docker-compose but translate tool not used in main flow")
    if 'grafana' in dc:
        grafana_provisioning = '../grafana/'
        if not os.path.exists(grafana_provisioning):
            log_warn(dc_path, 0, "Grafana in docker-compose but no provisioning configs - dead service")

# ========== 6. CHECK RATE LIMITING ==========
print(f"\n{BLUE}[6/10] RATE LIMITING CHECK{RESET}")
requirements_path = 'requirements.txt'
if os.path.exists(requirements_path):
    with open(requirements_path, 'r') as fp:
        reqs = fp.read()
    if 'fastapi-limiter' in reqs:
        # Check if used
        found_usage = False
        for fpath in py_files:
            if 'api' in fpath.lower():
                with open(fpath, 'r', encoding='utf-8') as fp:
                    if 'limiter' in fp.read().lower():
                        found_usage = True
        if not found_usage:
            log_issue(requirements_path, 0, "fastapi-limiter installed but NOT USED anywhere in code")

# ========== 7. CHECK TESTS ==========
print(f"\n{BLUE}[7/10] TEST CHECK{RESET}")
test_dir = '../tests'
if os.path.exists(test_dir):
    test_files = []
    for root, dirs, files in os.walk(test_dir):
        for f in files:
            if f.endswith('.py'):
                test_files.append(os.path.join(root, f))
    log_pass(f"Found {len(test_files)} test files")
    # Check coverage
    if not any('cov' in f for f in os.listdir(test_dir) if f.endswith('.ini')):
        log_warn(test_dir, 0, "No coverage config found (pytest-cov)")
else:
    log_issue('..', 0, "tests/ directory not found")

# ========== 8. CHECK SECURITY ==========
print(f"\n{BLUE}[8/10] SECURITY CHECK{RESET}")
# Check for hardcoded secrets
for fpath in py_files:
    with open(fpath, 'r', encoding='utf-8') as fp:
        lines = fp.readlines()
    for i, line in enumerate(lines, 1):
        if re.search(r'(api_key|secret|password)\s*=\s*["\']\w+["\']', line, re.IGNORECASE):
            if 'example' not in line.lower() and 'mock' not in line.lower():
                log_warn(fpath, i, "Possible hardcoded secret")

# ========== 9. CHECK IMPORTS ==========
print(f"\n{BLUE}[9/10] IMPORT CHECK (critical modules){RESET}")
critical_imports = {
    'pgvector': 'pgvector',
    'sentence_transformers': 'sentence-transformers',
    'rank_bm25': 'rank-bm25',
    'langgraph': 'langgraph',
    'fastapi': 'fastapi',
}
for module, package in critical_imports.items():
    try:
        __import__(module)
        log_pass(f"Import: {module} OK")
    except ImportError:
        log_warn('..', 0, f"Module '{module}' not installed (pip install {package})")

# ========== 10. CHECK KNOWLEDGE BASE ==========
print(f"\n{BLUE}[10/10] KNOWLEDGE BASE CHECK{RESET}")
kb_dir = '../backend/data/knowledge_base/'
if os.path.exists(kb_dir):
    txt_files = [f for f in os.listdir(kb_dir) if f.endswith('.txt')]
    log_pass(f"Knowledge base: {len(txt_files)} .txt files found")
    # Check if seed script exists
    if not os.path.exists('../backend/scripts/seed_kb.py'):
        log_issue('..', 0, "Knowledge base exists but seed_kb.py not found")
else:
    log_warn('..', 0, "Knowledge base directory not found")

# ========== PRINT RESULTS ==========
print(f"\n{BLUE}{'='*60}{RESET}")
print(f"{RED}ISSUES (MUST FIX): {len(issues)}{RESET}")
for i in issues:
    print(i)

print(f"\n{YELLOW}WARNINGS (SHOULD FIX): {len(warnings)}{RESET}")
for w in warnings:
    print(w)

print(f"\n{GREEN}PASSED: {len(passed)}{RESET}")
for p in passed:
    print(p)

print(f"\n{BLUE}{'='*60}{RESET}")
total_issues = len(issues) + len(warnings)
if total_issues == 0:
    print(f"{GREEN}ALL CHECKS PASSED - PRODUCTION READY{RESET}")
else:
    print(f"{RED}TOTAL ISSUES: {total_issues}{RESET}")
    print(f"{YELLOW}Fix all issues before pushing to GitHub for 50LPA{RESET}")

sys.exit(0 if total_issues == 0 else 1)
