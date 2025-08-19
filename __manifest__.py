{
    'name': 'POS Administration',
    'version': '15.0.1.0.0',
    'summary': 'Administration POS: validation des sorties de stock et intégration avec pos_livraison/pos_caisse',
    'author': 'Votre Nom',
    'category': 'Point of Sale',
    'depends': ['base', 'pos_caisse', 'pos_livraison'],
    'data': [
        'security/pos_admin_security.xml',
        'security/ir.model.access.csv',
        'data/pos_admin_data.xml',
        'views/pos_admin_views.xml',
        'views/pos_admin_menu.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
