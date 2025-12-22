# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EprRfq(models.Model):
    _name = 'epr.rfq'
    _description = 'EPR Request for Quotation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    # === 1. IDENTIFICATION ===
    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New')
    )

    active = fields.Boolean(default=True)

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('sent', 'Sent'),
            ('received', 'Received'),      # Nhà cung cấp đã báo giá
            ('to_approve', 'To Approve'),  # Trình sếp duyệt giá
            ('confirmed', 'Confirmed'),    # Đã duyệt -> Sẵn sàng tạo PO
            ('cancel', 'Cancelled')
        ],
        string='Status',
        readonly=True,
        index=True,
        copy=False,
        default='draft',
        tracking=True
    )

    approval_ids = fields.One2many(
        comodel_name='epr.approval.entry',
        inverse_name='rfq_id',
        string='Approval Steps'
    )

    # Tính tổng tiền trên RFQ để so sánh trong approval process
    amount_total = fields.Monetary(
        compute='_compute_amount_total',
        string='Total',
        currency_field='currency_id'
    )

    # === 2. RELATIONS ===
    # Link ngược lại PR gốc (01 RFQ có thể gom nhiều PR)
    request_ids = fields.Many2many(
        comodel_name='epr.purchase.request',
        relation='epr_rfq_purchase_request_rel',  # Tên bảng trung gian
        column1='rfq_id',
        column2='request_id',
        string='Source Requests',
        # Chỉ lấy các PR đã duyệt để tạo RFQ
        domain="[('state', '=', 'approved')]"
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        required=True,
        tracking=True
        # domain="[('supplier_rank', '>', 0)]",  # Chỉ chọn đã từng được chọn qua ít nhất 01 lần
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        readonly=True
    )

    # === 3. DATES ===
    date_order = fields.Datetime(
        string='Order Date', 
        default=fields.Datetime.now,
        readonly=True
    )

    date_deadline = fields.Date(
        string='Bid Deadline',
        help="Ngày hạn chót Vendor phải gửi báo giá",
        readonly=True
    )

    # === 4. LINES & PURCHASES ===
    line_ids = fields.One2many(
        comodel_name='epr.rfq.line',
        inverse_name='rfq_id',
        string='Products',
        copy=True
    )

    # Link sang Purchase Order gốc của Odoo
    purchase_ids = fields.One2many(
        comodel_name='purchase.order',
        inverse_name='epr_rfq_id',
        string='Purchase Orders'
    )

    purchase_count = fields.Integer(
        compute='_compute_purchase_count',
        string='PO Count'
    )

    request_count = fields.Integer(
        compute='_compute_request_count',
        string='PR Count'
    )

    # === 5. COMPUTE METHODS ===
    @api.depends('purchase_ids')
    def _compute_purchase_count(self):
        for rfq in self:
            rfq.purchase_count = len(rfq.purchase_ids)

    # Link ngược về PR gốc
    @api.depends('request_ids')
    def _compute_request_count(self):
        for rfq in self:
            rfq.request_count = len(rfq.request_ids)

    # === 6. CRUD OVERRIDES ===
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('epr.rfq') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.subtotal')
    def _compute_amount_total(self):
        for rfq in self:
            rfq.amount_total = sum(rfq.line_ids.mapped('subtotal'))

    # -------------------------------------------------------------------------
    # 7. ACTIONS
    # -------------------------------------------------------------------------
    def action_send_email(self):
        """Gửi email RFQ cho Vendor"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_("Chỉ có thể gửi RFQ khi ở trạng thái Draft."))
        self.write({'state': 'sent'})
        return True

    def action_mark_received(self):
        """Chuyển trạng thái sang Received khi nhận được phản hồi từ NCC"""
        for rfq in self:
            if rfq.state != 'sent':
                # Tư vấn: Nên chặn nếu nhảy cóc trạng thái để đảm bảo quy trình
                raise UserError(_("Chỉ có thể đánh dấu 'Đã nhận' khi RFQ đang ở trạng thái 'Đã gửi'."))
            rfq.write({'state': 'received'})

    def action_confirm_rfq(self):
        """Chốt RFQ, chuyển sang Confirmed"""
        for rfq in self:
            if rfq.state != 'received':
                raise UserError(_("Vui lòng chuyển sang trạng thái 'Đã nhận' trước khi xác nhận."))
            rfq.write({'state': 'confirmed'})

    def action_cancel_rfq(self):
        """Hủy RFQ ở bất kỳ trạng thái nào (trừ khi đã hủy rồi)"""
        for rfq in self:
            if rfq.state == 'cancel':
                continue

            # Nếu đã có PO liên kết, nên cảnh báo hoặc hủy luôn PO con
            if rfq.purchase_ids and any(po.state not in ['cancel'] for po in rfq.purchase_ids):
                raise UserError(_("Không thể hủy RFQ này vì đã có Đơn mua hàng (PO) được tạo. Vui lòng hủy PO trước."))

            rfq.write({'state': 'cancel'})

    def action_create_po(self):
        """Chuyển đổi RFQ này thành Purchase Order"""
        self.ensure_one()
        if not self.line_ids:
            raise ValidationError(_("Vui lòng thêm sản phẩm trước khi tạo PO."))

        # Logic tạo PO
        po_vals = {
            'partner_id': self.partner_id.id,
            'date_order': fields.Datetime.now(),
            'epr_rfq_id': self.id,  # Link ngược lại RFQ này
            'origin': self.name,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'order_line': []
        }

        for line in self.line_ids:
            po_vals['order_line'].append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.name,
                'product_qty': line.quantity,
                'price_unit': line.price_unit,
                'product_uom': line.uom_id.id,
                'date_planned': fields.Datetime.now(),
            }))

        new_po = self.env['purchase.order'].create(po_vals)

        self.write({'state': 'confirmed'})

        # Mở view PO vừa tạo
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': new_po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        """Cho phép quay lại Draft nếu cần sửa"""
        for rfq in self:
            if rfq.state not in ['sent', 'to_approve', 'cancel']:
                raise UserError(_("Chỉ có thể reset khi ở trạng thái Sent, To Approve hoặc Cancel."))
            rfq.write({'state': 'draft'})

    # Mở danh sách các PO được tạo từ RFQ này
    def action_view_purchase_orders(self):
        """Mở danh sách các Purchase Orders (PO) được tạo từ RFQ này"""
        self.ensure_one()
        return {
            'name': _('Purchase Orders'),
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'view_mode': 'list,form',
            # Filter các PO có field epr_rfq_id khớp với ID hiện tại
            'domain': [('epr_rfq_id', '=', self.id)],
            'context': {'default_epr_rfq_id': self.id},
            'target': 'current',
        }

    # Mở danh sách các PR gốc của RFQ này
    def action_view_source_requests(self):
        """Mở danh sách các PR gốc của RFQ này"""
        self.ensure_one()
        return {
            'name': _('Source Purchase Requests'),
            'type': 'ir.actions.act_window',
            'res_model': 'epr.purchase.request',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.request_ids.ids)],
            'target': 'current',
        }
    # -------------------------------------------------------------------------
    # RFQ APPROVAL PROCESS
    # -------------------------------------------------------------------------

    def action_submit_approval(self):
        """Nút bấm Submit for Approval"""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_("Vui lòng nhập chi tiết sản phẩm trước khi trình duyệt."))

        # 1. Tìm các Rules phù hợp
        configs = self.env['epr.approval.config'].search([
            ('active', '=', True),
            ('company_id', '=', self.company_id.id),
            ('min_amount', '<=', self.amount_total)
        ], order='sequence asc')

        if not configs:
            # Nếu không có rule nào -> Auto Approve
            self.write({'state': 'received'})  # Hoặc trạng thái tiếp theo bạn muốn
            return

        # 2. Xóa dữ liệu duyệt cũ (nếu submit lại)
        self.approval_ids.unlink()

        # 3. Tạo Approval Entries (Snapshot)
        approval_vals = []
        for conf in configs:
            approval_vals.append({
                'rfq_id': self.id,
                'config_id': conf.id,  # Nếu bạn muốn link lại
                'name': conf.name,
                'sequence': conf.sequence,
                'approval_type': conf.approval_type,
                'required_user_ids': [(6, 0, conf.user_ids.ids)],
                'status': 'new',  # Mặc định là new
            })

        self.env['epr.approval.entry'].create(approval_vals)

        # 4. Chuyển trạng thái và Kích hoạt tầng đầu tiên
        self.write({'state': 'to_approve'})
        self._check_approval_progression()

    # -------------------------------------------------------------------------
    # APPROVAL LOGIC: LINEARIZATION
    # -------------------------------------------------------------------------
    def _check_approval_progression(self):
        """Hàm này được gọi mỗi khi có 1 dòng được Approved hoặc khi mới Submit"""
        self.ensure_one()

        # Lấy tất cả entries
        all_entries = self.approval_ids

        # 1. Tìm các Sequence đang 'pending' (Đang chạy)
        current_pending = all_entries.filtered(lambda x: x.status == 'pending')

        if current_pending:
            # Nếu còn dòng đang pending -> Chưa làm gì cả, đợi user khác duyệt tiếp
            return

        # 2. Nếu không còn pending, tìm Sequence nhỏ nhất đang là 'new' (Chưa chạy)
        next_new_entries = all_entries.filtered(lambda x: x.status == 'new')

        if next_new_entries:
            # Tìm số sequence nhỏ nhất tiếp theo
            min_seq = min(next_new_entries.mapped('sequence'))

            # Kích hoạt TOÀN BỘ các rule có cùng sequence đó (Parallel Approval)
            to_activate = next_new_entries.filtered(lambda x: x.sequence == min_seq)
            to_activate.write({'status': 'pending'})

            # Gửi thông báo/Email cho những người vừa được kích hoạt (Optional)
            # self._notify_approvers(to_activate)
        else:
            # 3. Không còn 'new', cũng không còn 'pending' -> Tất cả đã Approved
            # Chuyển RFQ sang bước tiếp theo
            self.action_mark_approved()

    def action_mark_approved(self):
        """Hoàn tất quy trình duyệt"""
        # Chuyển sang trạng thái 'Confirmed'
        self.write({'state': 'confirmed'}) 
        self.message_post(body=_("Tất cả các cấp phê duyệt đã hoàn tất."))

    def action_reject_approval(self):
        """Xử lý khi bị từ chối"""
        self.write({'state': 'draft'})  # Quay về nháp để sửa
        self.message_post(body=_("Yêu cầu phê duyệt đã bị từ chối."))

# ==============================================================================
# CLASS CON: epr.rfq.line (Chi tiết hàng hóa trong RFQ)
# ==============================================================================


class EprRfqLine(models.Model):
    _name = 'epr.rfq.line'
    _description = 'EPR RFQ Line'

    rfq_id = fields.Many2one(
        comodel_name='epr.rfq',
        string='RFQ Reference',
        required=True,
        ondelete='cascade',
        index=True
    )

    # === LIÊN KẾT VỚI PR (QUAN TRỌNG) ===
    # Link về dòng chi tiết của PR gốc
    pr_line_id = fields.Many2one(
        'epr.purchase.request.line',
        string='Source PR Line',
        ondelete='set null',
        index=True,
        help="Dòng yêu cầu mua hàng gốc sinh ra dòng báo giá này."
    )

    # Link về PR Header (Tiện ích để group/filter)
    purchase_request_id = fields.Many2one(
        related='pr_line_id.request_id',
        string='Purchase Request',
        store=True,
        readonly=True
    )

    # === SẢN PHẨM & CHI TIẾT ===
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        required=True
    )

    description = fields.Text(string='Description')

    quantity = fields.Float(
        string='Quantity',
        required=True,
        default=1.0,
        digits='Product Unit of Measure'
    )

    uom_id = fields.Many2one(
        comodel_name='uom.uom',
        string='UoM',
        required=True
    )

    price_unit = fields.Float(
        string='Unit Price',
        digits='Product Price'
    )

    taxes_id = fields.Many2many(
        comodel_name='account.tax',
        relation='epr_rfq_line_taxes_rel',
        column1='line_id',
        column2='tax_id',
        string='Taxes',
        context={'active_test': False}
    )

    # === TÍNH TOÁN TIỀN TỆ ===
    currency_id = fields.Many2one(
        related='rfq_id.currency_id',
        store=True, 
        string='Currency',
        readonly=True
    )

    subtotal = fields.Monetary(
        compute='_compute_subtotal',
        string='Subtotal',
        store=True,
        currency_field='currency_id'
    )

    @api.depends('quantity', 'price_unit', 'taxes_id')
    def _compute_subtotal(self):
        """Tính tổng tiền (chưa bao gồm thuế)"""
        for line in self:
            line.subtotal = line.quantity * line.price_unit

    # === ONCHANGE PRODUCT (GỢI Ý) ===
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Tự động điền UoM và tên khi chọn sản phẩm"""
        if self.product_id:
            self.uom_id = self.product_id.uom_po_id or self.product_id.uom_id
            self.description = self.product_id.display_name
            # Tự động lấy thuế mua hàng mặc định của sản phẩm
            self.taxes_id = self.product_id.supplier_taxes_id

    # ==============================================================================
    # LINE-LEVEL LINKING LOGIC (From RFQs to POs)
    # ==============================================================================

    # Link tới dòng của Purchase Order chuẩn Odoo
    purchase_line_id = fields.Many2one(
        'purchase.order.line',
        string='Purchase Order Line',
        readonly=True,
        copy=False
    )

    # Tiện ích để xem nhanh trạng thái
    po_id = fields.Many2one(
        related='purchase_line_id.order_id',
        string='Purchase Order',
        store=True,
        readonly=True
    )
