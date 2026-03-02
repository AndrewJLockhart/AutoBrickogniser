from app import session
from bs4 import BeautifulSoup
import re
url='https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page?M=njo0413&tab=V'
r=session.get(url, timeout=30)
soup=BeautifulSoup(r.text,'html.parser')
text=soup.get_text('\n', strip=True)
ci = text.lower().find('current items')
print('current items index', ci)
if ci!=-1:
    cur_text = text[ci: ci+1000]
    print('---CUR TEXT---')
    print(cur_text)
    print('---AVG matches in cur_text---')
    for m in re.finditer(r'Avg Price:\s*\n?\s*(?:GBP|US\s*\$|USD\s*\$|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', cur_text, re.IGNORECASE):
        print('match', m.group(1), 'at', m.start())
    print('---MAX matches in cur_text---')
    for m in re.finditer(r'Max Price:\s*\n?\s*(?:GBP|US\s*\$|USD\s*\$|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', cur_text, re.IGNORECASE):
        print('match', m.group(1), 'at', m.start())
else:
    print('no current items')
