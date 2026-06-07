# ruff: noqa: E501  (data-heavy fixture file)
"""Capability-gradient tasks for the model-tier heterogeneity arena (GOALS heterogeneity round).

Unlike the cross-file ceiling-breakers (which test CONTEXT routing), these test MODEL CAPABILITY:
self-contained problems of rising intrinsic difficulty where a cheap model may fail and a strong
one may succeed — so model-tier routing (haiku->sonnet->opus) has something real to exploit. All
are minimal-context (no cross-file trick); the only lever is model strength. Hidden tests held out.
"""

from __future__ import annotations

from evals.metarouter_arena.schema import ArenaTaskSpec


def _t(name, diff, module, buggy, fixed, pub, hid, issue, ttype="bugfix"):
    return ArenaTaskSpec(name=name, task_type=ttype, risk_level="medium", difficulty_band=diff,
                         context_need="none", module_path=module, buggy=buggy, fixed=fixed,
                         public_test=pub, hidden_test=hid, issue_text=issue)


def capability_tasks() -> list[ArenaTaskSpec]:
    out = []
    # --- easy (all tiers should pass) ---
    out.append(_t("cap_reverse", "easy", "r.py",
        "def rev(s):\n    return s\n", "def rev(s):\n    return s[::-1]\n",
        "from r import rev\n\ndef test_pub():\n    assert rev('abc') == 'cba'\n",
        "from r import rev\n\ndef test_hid():\n    assert rev('') == '' and rev('xy') == 'yx'\n",
        "rev(s) should reverse the string."))
    out.append(_t("cap_fizz", "easy", "f.py",
        "def fizz(n):\n    return str(n)\n",
        "def fizz(n):\n    if n%15==0: return 'FizzBuzz'\n    if n%3==0: return 'Fizz'\n    if n%5==0: return 'Buzz'\n    return str(n)\n",
        "from f import fizz\n\ndef test_pub():\n    assert fizz(15)=='FizzBuzz'\n",
        "from f import fizz\n\ndef test_hid():\n    assert fizz(3)=='Fizz' and fizz(5)=='Buzz' and fizz(7)=='7'\n",
        "fizz(n): FizzBuzz rule."))
    # --- medium (algorithmic) ---
    out.append(_t("cap_roman", "medium", "rom.py",
        "def to_roman(n):\n    return ''\n",
        "def to_roman(n):\n    v=[(1000,'M'),(900,'CM'),(500,'D'),(400,'CD'),(100,'C'),(90,'XC'),(50,'L'),(40,'XL'),(10,'X'),(9,'IX'),(5,'V'),(4,'IV'),(1,'I')]\n    o=''\n    for x,s in v:\n        while n>=x:\n            o+=s; n-=x\n    return o\n",
        "from rom import to_roman\n\ndef test_pub():\n    assert to_roman(4)=='IV'\n",
        "from rom import to_roman\n\ndef test_hid():\n    assert to_roman(1994)=='MCMXCIV' and to_roman(49)=='XLIX'\n",
        "Implement to_roman(n) with subtractive notation (1..3999)."))
    out.append(_t("cap_intervals", "medium", "iv.py",
        "def merge(intervals):\n    return intervals\n",
        "def merge(intervals):\n    s=sorted(intervals); out=[]\n    for a,b in s:\n        if out and a<=out[-1][1]:\n            out[-1]=(out[-1][0],max(out[-1][1],b))\n        else:\n            out.append((a,b))\n    return out\n",
        "from iv import merge\n\ndef test_pub():\n    assert merge([(1,3),(2,6),(8,10)])==[(1,6),(8,10)]\n",
        "from iv import merge\n\ndef test_hid():\n    assert merge([(1,4),(4,5)])==[(1,5)] and merge([(5,6),(1,3),(2,4)])==[(1,4),(5,6)]\n",
        "merge(intervals): merge overlapping intervals."))
    # --- hard (subtle correctness; cheap models often slip) ---
    out.append(_t("cap_lengthOfLIS", "hard", "lis.py",
        "def lis(nums):\n    return len(nums)\n",
        "import bisect\ndef lis(nums):\n    t=[]\n    for x in nums:\n        i=bisect.bisect_left(t,x)\n        if i==len(t): t.append(x)\n        else: t[i]=x\n    return len(t)\n",
        "from lis import lis\n\ndef test_pub():\n    assert lis([10,9,2,5,3,7,101,18])==4\n",
        "from lis import lis\n\ndef test_hid():\n    assert lis([0,1,0,3,2,3])==4 and lis([7,7,7])==1 and lis([])==0\n",
        "lis(nums): length of the longest strictly-increasing subsequence."))
    out.append(_t("cap_editdist", "hard", "ed.py",
        "def edit(a,b):\n    return abs(len(a)-len(b))\n",
        "def edit(a,b):\n    m,n=len(a),len(b)\n    dp=list(range(n+1))\n    for i in range(1,m+1):\n        prev=dp[0]; dp[0]=i\n        for j in range(1,n+1):\n            cur=dp[j]\n            dp[j]=prev if a[i-1]==b[j-1] else 1+min(prev,dp[j],dp[j-1])\n            prev=cur\n    return dp[n]\n",
        "from ed import edit\n\ndef test_pub():\n    assert edit('horse','ros')==3\n",
        "from ed import edit\n\ndef test_hid():\n    assert edit('intention','execution')==5 and edit('','abc')==3 and edit('abc','abc')==0\n",
        "edit(a,b): Levenshtein edit distance."))
    out.append(_t("cap_calc", "hard", "cc.py",
        "def calc(s):\n    return 0\n",
        "def calc(s):\n    def ev(it):\n        stack=[]; num=0; sign='+'\n        while True:\n            c=next(it,None)\n            if c is not None and c.isdigit(): num=num*10+int(c)\n            elif c=='(': num=ev(it)\n            if c is None or c in '+-*/)':\n                if sign=='+': stack.append(num)\n                elif sign=='-': stack.append(-num)\n                elif sign=='*': stack.append(stack.pop()*num)\n                elif sign=='/': stack.append(int(stack.pop()/num))\n                sign=c; num=0\n                if c==')' or c is None: break\n        return sum(stack)\n    return ev(iter(s.replace(' ','')))\n",
        "from cc import calc\n\ndef test_pub():\n    assert calc('2+3*4')==14\n",
        "from cc import calc\n\ndef test_hid():\n    assert calc('(2+3)*4')==20 and calc('10-2*3')==4 and calc('2*(3+(4*5))')==46\n",
        "calc(s): evaluate an integer arithmetic expression with + - * / and parentheses (no eval)."))
    out.append(_t("cap_json", "hard", "jp.py",
        "def parse(s):\n    return None\n",
        "import json\ndef parse(s):\n    return json.loads(s)\n",
        "from jp import parse\n\ndef test_pub():\n    assert parse('{\"a\": 1}')=={'a':1}\n",
        "from jp import parse\n\ndef test_hid():\n    assert parse('[1,2,[3]]')==[1,2,[3]] and parse('{\"x\":[true,null]}')=={'x':[True,None]}\n",
        "parse(s): parse a JSON string to Python objects."))
    return out


def hard_capability_tasks() -> list[ArenaTaskSpec]:
    """Edge-case-dense tasks (not memorized one-liners) where a weak model is likelier to slip.

    These deliberately avoid the 'hide the answer in another file' trick: every task is fully
    self-contained and well-specified. The lever is intrinsic problem difficulty + edge-case
    density (clamping, grammar corners, off-by-one) — exactly what should separate model tiers if
    a gap exists. Hidden tests probe the corners; the public test shows only the happy path.
    """
    out = []
    out.append(_t("cap_atoi", "hard", "ai.py",
        "def my_atoi(s):\n    return int(s)\n",
        "def my_atoi(s):\n    s=s.lstrip(); i=0; sign=1\n    if i<len(s) and s[i] in '+-':\n        sign=-1 if s[i]=='-' else 1; i+=1\n    num=0\n    while i<len(s) and s[i].isdigit():\n        num=num*10+int(s[i]); i+=1\n    num*=sign\n    return max(-2**31, min(2**31-1, num))\n",
        "from ai import my_atoi\n\ndef test_pub():\n    assert my_atoi('42')==42\n",
        "from ai import my_atoi\n\ndef test_hid():\n    assert my_atoi('   -42')==-42 and my_atoi('4193 with words')==4193 and my_atoi('words 9')==0 and my_atoi('-91283472332')==-2147483648 and my_atoi('2147483648')==2147483647\n",
        "my_atoi(s): parse a leading integer like C atoi — skip leading spaces, optional sign, read digits until non-digit, then CLAMP to signed 32-bit range [-2**31, 2**31-1]. Non-numeric start -> 0."))
    out.append(_t("cap_valid_number", "hard", "vn.py",
        "def is_number(s):\n    return s.isdigit()\n",
        "import re\ndef is_number(s):\n    return re.fullmatch(r'[+-]?(\\d+\\.?\\d*|\\.\\d+)([eE][+-]?\\d+)?', s) is not None\n",
        "from vn import is_number\n\ndef test_pub():\n    assert is_number('0') and not is_number('abc')\n",
        "from vn import is_number\n\ndef test_hid():\n    assert is_number('3.') and is_number('.1') and is_number('46.e3') and is_number('+.8') and not is_number('e9') and not is_number('99e2.5') and not is_number('--6') and not is_number('1e')\n",
        "is_number(s): True iff s is a valid number: optional sign, then (digits with optional fraction) or (.digits), optional exponent (e/E, optional sign, >=1 digit). No surrounding whitespace."))
    out.append(_t("cap_wildcard", "hard", "wc.py",
        "def is_match(s,p):\n    return s==p\n",
        "import functools\ndef is_match(s,p):\n    @functools.lru_cache(None)\n    def dp(i,j):\n        if j==len(p): return i==len(s)\n        if p[j]=='*':\n            return dp(i,j+1) or (i<len(s) and dp(i+1,j))\n        if i<len(s) and (p[j]=='?' or p[j]==s[i]):\n            return dp(i+1,j+1)\n        return False\n    return dp(0,0)\n",
        "from wc import is_match\n\ndef test_pub():\n    assert is_match('aa','a*')\n",
        "from wc import is_match\n\ndef test_hid():\n    assert not is_match('cb','?a') and is_match('adceb','*a*b') and not is_match('acdcb','a*c?b') and is_match('','*') and is_match('','') and not is_match('a','')\n",
        "is_match(s,p): wildcard match where '?' matches any single char and '*' matches any sequence (including empty). Must match the ENTIRE string."))
    out.append(_t("cap_decode", "hard", "dc.py",
        "def num_decodings(s):\n    return len(s)\n",
        "def num_decodings(s):\n    if not s or s[0]=='0': return 0\n    n=len(s); a,b=1,1\n    for i in range(1,n):\n        cur=0\n        if s[i]!='0': cur+=b\n        if 10<=int(s[i-1:i+1])<=26: cur+=a\n        a,b=b,cur\n    return b\n",
        "from dc import num_decodings\n\ndef test_pub():\n    assert num_decodings('12')==2\n",
        "from dc import num_decodings\n\ndef test_hid():\n    assert num_decodings('226')==3 and num_decodings('0')==0 and num_decodings('06')==0 and num_decodings('10')==1 and num_decodings('100')==0 and num_decodings('2101')==1\n",
        "num_decodings(s): count ways to decode a digit string where 1..26 map to A..Z. '0' only valid as part of 10/20; leading 0 or invalid 0 -> 0 ways."))
    out.append(_t("cap_calc_unary", "hard", "cu.py",
        "def calc2(s):\n    return 0\n",
        "def calc2(s):\n    s=s.replace(' ',''); pos=0\n    def peek():\n        return s[pos] if pos<len(s) else ''\n    def expr():\n        nonlocal pos\n        v=term()\n        while peek() in ('+','-'):\n            op=s[pos]; pos+=1; t=term(); v=v+t if op=='+' else v-t\n        return v\n    def term():\n        nonlocal pos\n        v=factor()\n        while peek() in ('*','/'):\n            op=s[pos]; pos+=1; f=factor(); v=v*f if op=='*' else int(v/f)\n        return v\n    def factor():\n        nonlocal pos\n        if peek()=='+': pos+=1; return factor()\n        if peek()=='-': pos+=1; return -factor()\n        if peek()=='(':\n            pos+=1; v=expr(); pos+=1; return v\n        st=pos\n        while peek().isdigit(): pos+=1\n        return int(s[st:pos])\n    return expr()\n",
        "from cu import calc2\n\ndef test_pub():\n    assert calc2('1+2*3')==7\n",
        "from cu import calc2\n\ndef test_hid():\n    assert calc2('-(3+4)')==-7 and calc2('2*(3+-4)')==-2 and calc2('-2--3')==1 and calc2('((1+2))*3')==9 and calc2('10/3')==3\n",
        "calc2(s): evaluate +,-,*,/ with parentheses AND unary plus/minus (e.g. -2, 3+-4). Integer division truncates toward zero. No eval()."))
    out.append(_t("cap_circular_max", "hard", "cm.py",
        "def max_circular(nums):\n    return max(nums) if nums else 0\n",
        "def max_circular(nums):\n    if not nums: return 0\n    total=0; cmax=0; bmax=nums[0]; cmin=0; bmin=nums[0]\n    for x in nums:\n        cmax=max(x,cmax+x); bmax=max(bmax,cmax)\n        cmin=min(x,cmin+x); bmin=min(bmin,cmin); total+=x\n    return bmax if bmax<0 else max(bmax, total-bmin)\n",
        "from cm import max_circular\n\ndef test_pub():\n    assert max_circular([1,-2,3,-2])==3\n",
        "from cm import max_circular\n\ndef test_hid():\n    assert max_circular([5,-3,5])==10 and max_circular([-3,-2,-3])==-2 and max_circular([3,-1,2,-1])==4 and max_circular([2,-2,2,-2])==2\n",
        "max_circular(nums): maximum subarray sum where the array is CIRCULAR (the subarray may wrap around the end). If all numbers are negative, return the largest single element."))
    out.append(_t("cap_simplify_path", "hard", "sp.py",
        "def simplify(path):\n    return path\n",
        "def simplify(path):\n    st=[]\n    for p in path.split('/'):\n        if p=='' or p=='.': continue\n        if p=='..':\n            if st: st.pop()\n        else: st.append(p)\n    return '/'+'/'.join(st)\n",
        "from sp import simplify\n\ndef test_pub():\n    assert simplify('/home/')=='/home'\n",
        "from sp import simplify\n\ndef test_hid():\n    assert simplify('/../')=='/' and simplify('/a/./b/../../c/')=='/c' and simplify('/a//b////c/d//././/..')=='/a/b/c' and simplify('/')=='/'\n",
        "simplify(path): canonicalize a Unix absolute path — collapse '//', drop '.', resolve '..' (popping a dir, no-op at root), no trailing slash, always start with '/'."))
    out.append(_t("cap_excel_title", "hard", "et.py",
        "def col_title(n):\n    return chr(64+n)\n",
        "def col_title(n):\n    out=''\n    while n>0:\n        n,r=divmod(n-1,26); out=chr(65+r)+out\n    return out\n",
        "from et import col_title\n\ndef test_pub():\n    assert col_title(1)=='A'\n",
        "from et import col_title\n\ndef test_hid():\n    assert col_title(26)=='Z' and col_title(28)=='AB' and col_title(701)=='ZY' and col_title(702)=='ZZ' and col_title(703)=='AAA'\n",
        "col_title(n): convert a 1-indexed Excel column number to its letter title (bijective base-26; 1->A, 26->Z, 27->AA)."))
    return out


def heavy_capability_tasks() -> list[ArenaTaskSpec]:
    """Heavy, compositional tasks (more state / longer logic) — the best shot at a real tier gap.

    A bytecode VM, a full regex engine, N-Queens counting, and bounded coin-change: each needs
    several interacting pieces correct at once, where a weaker model is likeliest to compound a
    small error. Still fully self-contained and well-specified (no cross-file trick).
    """
    out = []
    out.append(_t("cap_vm", "hard", "vm.py",
        "def run(prog):\n    return []\n",
        "def run(prog):\n    pc=0; st=[]; out=[]\n    while 0<=pc<len(prog):\n        op=prog[pc]; n=op[0]\n        if n=='PUSH': st.append(op[1]); pc+=1\n        elif n=='ADD': b=st.pop(); a=st.pop(); st.append(a+b); pc+=1\n        elif n=='SUB': b=st.pop(); a=st.pop(); st.append(a-b); pc+=1\n        elif n=='MUL': b=st.pop(); a=st.pop(); st.append(a*b); pc+=1\n        elif n=='DUP': st.append(st[-1]); pc+=1\n        elif n=='SWAP': st[-1],st[-2]=st[-2],st[-1]; pc+=1\n        elif n=='PRINT': out.append(st[-1]); pc+=1\n        elif n=='JMP': pc=op[1]\n        elif n=='JZ': pc=op[1] if st.pop()==0 else pc+1\n        elif n=='HALT': break\n        else: pc+=1\n    return out\n",
        "from vm import run\n\ndef test_pub():\n    assert run([('PUSH',2),('PUSH',3),('ADD',),('PRINT',),('HALT',)])==[5]\n",
        "from vm import run\n\ndef test_hid():\n    # countdown 3,2,1 using JZ/JMP; then a SWAP/SUB check\n    cd=[('PUSH',3),('DUP',),('PRINT',),('PUSH',1),('SUB',),('DUP',),('JZ',8),('JMP',1),('HALT',)]\n    assert run(cd)==[3,2,1]\n    assert run([('PUSH',3),('PUSH',10),('SWAP',),('SUB',),('PRINT',),('HALT',)])==[7]\n",
        "run(prog): execute a stack bytecode VM. Ops (tuples): ('PUSH',n) push n; ('ADD'|'SUB'|'MUL') pop b then a, push a op b; ('DUP') duplicate top; ('SWAP') swap top two; ('PRINT') append top to output; ('JMP',i) set pc=i; ('JZ',i) pop v, jump to i if v==0 else continue; ('HALT') stop. Return the list of printed values."))
    out.append(_t("cap_regex", "hard", "re10.py",
        "def is_match(s,p):\n    return s==p\n",
        "import functools\ndef is_match(s,p):\n    @functools.lru_cache(None)\n    def dp(i,j):\n        if j==len(p): return i==len(s)\n        first = i<len(s) and p[j] in (s[i],'.')\n        if j+1<len(p) and p[j+1]=='*':\n            return dp(i,j+2) or (first and dp(i+1,j))\n        return first and dp(i+1,j+1)\n    return dp(0,0)\n",
        "from re10 import is_match\n\ndef test_pub():\n    assert is_match('aa','a*') and not is_match('aa','a')\n",
        "from re10 import is_match\n\ndef test_hid():\n    assert is_match('ab','.*') and is_match('aab','c*a*b') and not is_match('mississippi','mis*is*p*.') and is_match('','') and is_match('','a*') and not is_match('ab','.*c')\n",
        "is_match(s,p): full-string regex match where '.' matches any single char and '*' matches zero or more of the PRECEDING element (like '/' regex a*, .*). Must match the entire string."))
    out.append(_t("cap_nqueens", "hard", "nq.py",
        "def count(n):\n    return n\n",
        "def count(n):\n    res=0; cols=set(); d1=set(); d2=set()\n    def bt(r):\n        nonlocal res\n        if r==n: res+=1; return\n        for c in range(n):\n            if c in cols or (r-c) in d1 or (r+c) in d2: continue\n            cols.add(c); d1.add(r-c); d2.add(r+c)\n            bt(r+1)\n            cols.discard(c); d1.discard(r-c); d2.discard(r+c)\n    bt(0)\n    return res\n",
        "from nq import count\n\ndef test_pub():\n    assert count(4)==2\n",
        "from nq import count\n\ndef test_hid():\n    assert count(1)==1 and count(2)==0 and count(3)==0 and count(5)==10 and count(6)==4 and count(8)==92\n",
        "count(n): number of distinct solutions to the N-Queens problem on an n x n board."))
    out.append(_t("cap_min_coins", "hard", "mc.py",
        "def min_coins(coins, amount):\n    return amount\n",
        "def min_coins(coins, amount):\n    INF=float('inf'); dp=[0]+[INF]*amount\n    for a in range(1,amount+1):\n        for c in coins:\n            if c<=a and dp[a-c]+1<dp[a]: dp[a]=dp[a-c]+1\n    return -1 if dp[amount]==INF else dp[amount]\n",
        "from mc import min_coins\n\ndef test_pub():\n    assert min_coins([1,2,5],11)==3\n",
        "from mc import min_coins\n\ndef test_hid():\n    assert min_coins([2],3)==-1 and min_coins([1],0)==0 and min_coins([2,5,10,1],27)==4 and min_coins([186,419,83,408],6249)==20\n",
        "min_coins(coins, amount): fewest coins (unlimited supply of each denomination) summing to amount; return -1 if impossible, 0 for amount 0."))
    return out


def all_capability_tasks() -> list[ArenaTaskSpec]:
    return capability_tasks() + hard_capability_tasks() + heavy_capability_tasks()
