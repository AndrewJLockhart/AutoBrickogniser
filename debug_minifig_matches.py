from app import session
from bs4 import BeautifulSoup
import re
url='https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page?M=njo0413&tab=V'
r=session.get(url, timeout=30)
soup=BeautifulSoup(r.text,'html.parser')
text=soup.get_text('\n', strip=True)
idx=text.lower().find('last 6 months')
last6=''
if idx!=-1:
    last6=text[idx: idx+2000]
    print('---LAST6 START---')
    print(last6)
    print('---AVG PRICE MATCHES---')
    for m in re.finditer(r'Avg Price:\s*\n?\s*(?:GBP|US\s*\$|USD\s*\$|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', last6, re.IGNORECASE):
        print('match:', m.group(1), 'at', m.start())
else:
    print('no last6')

print('\n---ALL Avg Price in page---')
for m in re.finditer(r'Avg Price:\s*\n?\s*(?:GBP|US\s*\$|USD\s*\$|\$)?\s*([0-9,]+(?:\.[0-9]{1,2})?)', text, re.IGNORECASE):
    print('match:', m.group(1), 'at', m.start())
