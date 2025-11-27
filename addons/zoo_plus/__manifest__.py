{
    'name': 'Zoo Plus',
    'summary': """Zoo Plus""",
    'description': """Building a zoo plus - Inheritence from Zoo City""",
    'author': 'Truong Phan',
    'maintainer': 'Truong Phan',
    'category': 'Uncategorized',
    'version': '0.1',
    'depends': [
        'zoo', # <-- depends on zoo (parent - Folder name) addon
    ],
    'data': [
        'security/ir.model.access.csv',
    ],
    'demo': [],
    'css': [],
    # 'qweb': ['static/src/xml/*.xml'],
    'installable': True,
    'auto_install': False,
    'application': True,
}