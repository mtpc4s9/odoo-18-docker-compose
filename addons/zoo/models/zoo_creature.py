# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

class ZooCreature(models.Model):
    _name = "zoo.creature"
    _description = "Creature"
    
    name = fields.Char('Name', required=True)
    environment = fields.Selection([
        ('water', 'Water'),
        ('ground', 'Ground'),
        ('sky', 'Sky'),
    ], string='Environment', default='ground')
    is_rare = fields.Boolean('Is Rare', default=False)

    animal_ids = fields.One2many(comodel_name='zoo.animal', inverse_name='creature_id', string='Animals')