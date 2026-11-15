import html
import re
import unicodedata
from rapidfuzz.fuzz import ratio
from pylatexenc.latex2text import LatexNodes2Text

def plain(value):
    return html.unescape(LatexNodes2Text().latex_to_text(html.unescape(str(value or ''))))

def norm(value):
    value = unicodedata.normalize('NFKD', plain(value)).casefold()
    return ' '.join(re.sub(r'[^\w\s]', ' ', ''.join(c for c in value if not unicodedata.combining(c))).split())

def doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)', '', value)
    return value.rstrip('.,; ')

def similarity(a, b):
    return ratio(norm(a),norm(b))/100 if a and b else 0

def surnames(value):
    names = re.split(r'\s+and\s+', plain(value), flags=re.I)
    return [norm(n.split(',')[0] if ',' in n else n.split()[-1]) for n in names if n.strip()]

def authors_match(a, b):
    aa, bb = surnames(a), surnames(b)
    return bool(aa and aa == bb)

def venue_equivalent(a, b):
    aa, bb = norm(a), norm(b)
    if aa == bb:
        return True
    # Treat only matching token initials as a possible abbreviation, never proof of identity.
    ignored = {'of','the','and','on','for','in'}
    initials = lambda s: ''.join(w[0] for w in s.split() if w not in ignored)
    compact = lambda s: s.replace(' ','')
    return len(initials(aa)) >= 3 and (initials(aa) == compact(bb) or initials(bb) == compact(aa))
