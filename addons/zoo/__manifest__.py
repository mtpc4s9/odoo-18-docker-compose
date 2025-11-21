# -*- coding: utf-8 -*-
# https://www.odoo.com/documentation/18.0/developer/reference/backend/module.html
{
    'name': 'Zoo City',
    'summary': """Zoo City Tutorials""",
    'description': """Building my own zoo city""",
    'author': 'minhng.info',
    'maintainer': 'minhng.info',
    'website': 'https://minhng.info',
    'category': 'Uncategorized', # https://github.com/odoo/odoo/blob/18.0/odoo/addons/base/data/ir_module_category_data.xml
    'version': '0.1',
    'depends': [
        'product',
    ],
    'data': [],
    'demo': [],
    'css': [],
    # 'qweb': ['static/src/xml/*.xml'],
    'installable': True,
    'auto_install': False,
    'application': True,

    # Depends declaration
    'depends': [
        'product',
        'mail',
    ],

    # Data files declaration
    'data': [
        'security/ir.model.access.csv',
        'views/zoo_animal_views.xml',
        'views/zoo_creature_views.xml',
        'views/zoo_cage_views.xml',
        'views/zoo_health_records.xml',
        'views/zoo_diet_plans.xml',
    ],
}