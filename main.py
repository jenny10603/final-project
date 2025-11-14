import xml.etree.ElementTree as ET

tree = ET.parse('SuperMarket.xml')
root = tree.getroot()

for product in root.findall('product'):
    name = product.find('name').text
    print(f'Product Name: {name}')