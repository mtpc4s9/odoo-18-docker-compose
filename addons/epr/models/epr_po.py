# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    # === FIELD LIÊN KẾT 1-1 TỚI EPR RFQ ===
    # Dùng cho action_create_po() trong epr.rfq
    epr_rfq_id = fields.Many2one(
        comodel_name='epr.rfq', 
        string='Original ePR RFQ',
        readonly=True,
        copy=False,
        ondelete='set null',
        help="Tham chiếu đến phiếu báo giá nội bộ (ePR) đã tạo ra PO này."
    )

    # === COMPUTED FIELDS CHO SMART BUTTON (Line-Level Linking) ===
    # Tìm tất cả các RFQ gốc dựa trên các dòng PO lines
    epr_rfq_ids = fields.Many2many(
        comodel_name='epr.rfq',
        string='Source RFQs',
        compute='_compute_epr_rfq_data',
        help="Các phiếu yêu cầu báo giá (EPR RFQ) liên quan đến đơn mua hàng này."
    )

    epr_rfq_count = fields.Integer(
        string='RFQ Count',
        compute='_compute_epr_rfq_data'
    )

    @api.depends('order_line.epr_rfq_line_id')
    def _compute_epr_rfq_data(self):
        for po in self:
            # Logic: Quét qua tất cả line của PO -> lấy epr_rfq_line -> lấy rfq_id -> unique
            # Mapped tự động loại bỏ các giá trị trùng lặp (set)
            rfqs = po.order_line.mapped('epr_rfq_line_id.rfq_id')
            po.epr_rfq_ids = rfqs
            po.epr_rfq_count = len(rfqs)

    # === ACTION SMART BUTTON ===
    def action_view_epr_rfqs(self):
        """Mở danh sách các EPR RFQ nguồn"""
        self.ensure_one()
        return {
            'name': _('Source RFQs'),
            'type': 'ir.actions.act_window',
            'res_model': 'epr.rfq',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.epr_rfq_ids.ids)],
            'context': {'create': False},  # Không cho tạo mới RFQ từ đây để tránh mất quy trình
        }


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    # === FIELD LIÊN KẾT QUAN TRỌNG NHẤT ===
    # Field này sẽ được Wizard 'epr.create.po.wizard' ghi dữ liệu vào
    epr_rfq_line_id = fields.Many2one(
        comodel_name='epr.rfq.line',
        string='Source RFQ Line',
        readonly=True,
        copy=False,
        index=True,
        help="Dòng yêu cầu báo giá gốc đã tạo ra dòng đơn mua hàng này."
    )
