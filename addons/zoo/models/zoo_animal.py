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
    nickname = fields.Char('Nickname')
    introduction_vn = fields.Html('Introduction (VI)')
    is_purchased = fields.Boolean('Has Been Purchased', default=False)
    purchase_price = fields.Float('Purchase Price')
    parent_id = fields.Many2one(comodel_name='zoo.animal', string='Parent', ondelete='set null')
    male_children_ids = fields.One2many(comodel_name='zoo.animal', inverse_name='parent_id', string='Children')
    veterinarian_id = fields.Many2one(comodel_name='res.partner', string='Veterinarian')

    # thêm vào cuối:

    age = fields.Integer('Pet Age', compute='_compute_age')
    number_of_children = fields.Integer('Number of Children', compute='_compute_number_of_children')

    # thêm các trường quan hệ sau:
    mother_id = fields.Many2one(comodel_name='zoo.animal', string='Mother', ondelete='set null') # ondelete: 'set null', 'restrict', 'cascade'
    mother_name = fields.Char('Mother Name', related='mother_id.name')
    female_children_ids = fields.One2many(comodel_name='zoo.animal', inverse_name='mother_id', string='Female Children')

    toy_ids = fields.Many2many(comodel_name='product.product', 
                                string="Toys", 
                                relation='animal_product_toy_rel',
                                column1='col_animal_id',
                                column2='col_product_id')

    creature_id = fields.Many2one(comodel_name='zoo.creature', string='Creature')

    @api.depends('dob')
    def _compute_age(self):
        now = datetime.datetime.now()
        current_year = now.year
        for record in self:
            dob = record.dob
            if dob:
                dob_year = dob.year
                delta_year = current_year - dob_year
                if delta_year < 0:
                    raise ValidationError(_("Negative age: current year < DOB year!"))
                record.age = delta_year
            else:
                record.age = False
        pass

    @api.depends('male_children_ids')
    def _compute_number_of_children(self):
        for record in self:
            record.number_of_children = len(record.male_children_ids)

    @api.constrains('dob')
    def _check_dob(self):
        for record in self:
            if record.dob and record.dob.year < 1900:
                raise ValidationError(_("Invalid DOB!"))

    @api.onchange('weight')
    def _update_weight_pound(self):
        self.weight_pound = self.weight * 2.204623

    @api.onchange('weight_pound')
    def _update_weight_kg(self):
        self.weight = self.weight_pound / 2.204623