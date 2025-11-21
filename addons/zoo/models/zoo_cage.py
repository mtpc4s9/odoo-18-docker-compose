# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ZooCage(models.Model):
    _name = 'zoo.cage'
    _description = 'Zoo Cage'
    _order = 'name'

    name = fields.Char(string='Cage Name', required=True)
    capacity = fields.Integer(string='Capacity', help='Maximum number of animals')
    location = fields.Char(string='Location')
    cage_type = fields.Selection([
        ('indoor', 'Indoor'),
        ('outdoor', 'Outdoor'),
        ('aquarium', 'Aquarium'),
        ('aviary', 'Aviary'),
    ], string='Cage Type', default='outdoor')
    area = fields.Float(string='Area (m²)', help='Cage area in square meters')
    description = fields.Text(string='Description')
    active = fields.Boolean(string='Active', default=True)
