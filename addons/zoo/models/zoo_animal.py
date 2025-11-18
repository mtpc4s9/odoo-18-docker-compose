# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError

import datetime

class ZooAnimal(models.Model):
    _name = "zoo.animal"
    _description = "Animal in the zoo"

    name = fields.Char('Animal Name', required=True)    
    description = fields.Text('Description')
    dob = fields.Date('DOB', required=False)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female')
    ], string='Gender', default='male', required=True)
    feed_time = fields.Datetime('Feed Time', copy=False)
    is_alive = fields.Boolean('Is Alive', default=True)
    image = fields.Binary("Image", attachment=True, help="Animal Image")
    weight = fields.Float('Weight (kg)')
    weight_pound = fields.Float('Weight (pounds)')
    introduction = fields.Text('Introduction (EN)')    