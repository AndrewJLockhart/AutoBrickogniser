from app import session
from bs4 import BeautifulSoup
url='https://www.bricklink.com/v2/catalog/catalogitem_pgtab.page?M=njo0413&tab=V'
r=session.get(url, timeout=30)
print('Status', r.status_code)
soup=BeautifulSoup(r.text,'html.parser')
text=soup.get_text('\n', strip=True)
idx=text.lower().find('last 6 months')
if idx!=-1:
    print('\n---LAST 6 MONTHS SLICE---\n')
    print(text[idx: idx+1200])
else:
    print('No Last 6 Months found')
idx2=text.lower().find('current items')
if idx2!=-1:
    print('\n---CURRENT ITEMS SLICE---\n')
    print(text[idx2: idx2+1200])
else:
    print('No Current Items found')
