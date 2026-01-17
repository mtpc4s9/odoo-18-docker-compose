# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class LdTrainingRoom(models.Model):
    _name = 'ld.room'
    _description = 'Training Room / Venue'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name asc'

    # ==================================================================================
    # 1. BASIC INFO
    # ==================================================================================
    name = fields.Char(
        string='Room Name',
        required=True,
        index=True,
        tracking=True,
        help="E.g., Meeting Room A - Floor 2"
    )

    code = fields.Char(
        string='Room Code',
        copy=False,
        tracking=True,
        help="Unique Asset Code (e.g., RM-001) for facility management."
    )

    active = fields.Boolean(
        default=True,
        help="Archive this room if it is under maintenance or no longer available."
    )

    room_type = fields.Selection(
        selection=[
            ('physical', 'Physical Room'),
            ('virtual', 'Virtual/Online'),
            ('external', 'External Venue')
        ],
        string='Room Type',
        default='physical',
        required=True,
        tracking=True
    )

    # ==================================================================================
    # 2. CAPACITY & LAYOUT
    # ==================================================================================
    capacity = fields.Integer(
        string='Max Capacity',
        default=20,
        required=True,
        help="Maximum number of attendees allowed."
    )

    seating_style = fields.Selection(
        selection=[
            ('classroom', 'Classroom'),
            ('fan', 'Fan-Type'),
            ('conference', 'Conference'),
            ('horseshoe', 'Horseshoe'),
            ('u_shape', 'U-Shape')
        ],
        string='Seating Layout',
        default='classroom',
        help="Layout affects the training methodology (Lecture vs Group Discussion)."
    )

    # ==================================================================================
    # 3. LOGISTICS & TECH
    # ==================================================================================
    is_video_conf = fields.Boolean(
        string='Video Conf. Ready',
        help="Check if the room is equipped with VC hardware (Screens, Polycom, etc.)."
    )

    access_url = fields.Char(
        string='Access URL',
        help="Permanent link for Virtual Rooms (e.g., Fixed Zoom Room)."
    )

    address = fields.Char(
        string='Address/Location',
        help="Detailed physical address (Building, Floor)."
    )

    # ==================================================================================
    # 4. MANAGEMENT
    # ==================================================================================
    manager_id = fields.Many2one(
        comodel_name='res.users',
        string='Room Manager',
        tracking=True,
        help="Person responsible for keys, setup, and maintenance."
    )

    cost_per_hour = fields.Float(
        string='Cost per Hour',
        digits='Product Price',
        help="Internal chargeback cost or rental fee."
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # ==================================================================================
    # 5. STATISTICS (Smart Button)
    # ==================================================================================
    session_count = fields.Integer(
        string='Session Count',
        compute='_compute_session_count',
        help="Number of training sessions conducted in this room."
    )

    # ==================================================================================
    # COMPUTE METHODS
    # ==================================================================================
    def _compute_session_count(self):
        # Count sessions where this room is used
        Session = self.env['ld.session']
        for record in self:
            record.session_count = Session.search_count([('location_id', '=', record.id)])

    # ==================================================================================
    # CONSTRAINTS
    # ==================================================================================
    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'The Room Code must be unique!'),
        ('check_capacity', 'CHECK(capacity > 0)', 'Capacity must be greater than 0.')
    ]

    @api.constrains('room_type', 'access_url', 'address')
    def _check_room_logistics(self):
        for record in self:
            # 1. Virtual Rooms must have a URL (or at least encouraged)
            if record.room_type == 'virtual' and not record.access_url:
                # Warning only or strict? Let's be strict for data quality.
                # raise ValidationError(_("Virtual rooms must have an Access URL."))
                pass 

            # 2. Physical Rooms should have an address
            if record.room_type == 'physical' and not record.address:
                # Just a warning log usually, but here we enforce logic if needed
                pass

    # ==================================================================================
    # SMART BUTTON ACTIONS
    # ==================================================================================
    def action_view_sessions(self):
        """ Open the list/calendar of sessions booked in this room """
        self.ensure_one()
        return {
            'name': _('Sessions in %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'ld.session',
            'view_mode': 'calendar,list,form',
            'domain': [('location_id', '=', self.id)],
            'context': {'default_location_id': self.id}
        }
