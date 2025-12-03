# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EprPurchaseRequest(models.Model):
    _name = 'epr.purchase.request'
    _description = 'Electronic Purchase Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(
        string='Request Reference',
        required=True,
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )

    active = fields.Boolean(
        string='Active',
        default=True
    )

    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        tracking=True,
        default=lambda self: self.env.user.employee_id
    )

    department_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        related='employee_id.department_id',
        store=True,
        readonly=True
    )

    date_required = fields.Date(
        string='Date Required',
        required=True,
        tracking=True,
        default=fields.Date.context_today
    )
    priority = fields.Selection(
        [('1', 'Low'), ('2', 'Medium'), ('3', 'High'), ('4', 'Very High')],
        string='Priority',
        default='1',
        tracking=True
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('to_approve', 'To Approve'),
            ('approved', 'Approved'),
            ('in_progress', 'In Progress'),
            ('done', 'Done'),
            ('rejected', 'Rejected'),
            ('cancel', 'Cancelled')
        ],
        string='Status',
        default='draft',
        tracking=True,
        index=True,
        copy=False
    )

    # approver_ids = fields.Many2many(
    #     'res.users',
    #     string='Approvers',
    #     compute='_compute_approvers',
    #     store=True
    # )

    # Approvers: Nên là field thường (không compute) để lưu cố định người duyệt lúc Submit
    approver_ids = fields.Many2many(
        comodel_name='res.users',
        string='Approvers',
        copy=False
    )

    rejection_reason = fields.Text(
        string='Rejection Reason',
        readonly=True,
        tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    line_ids = fields.One2many(
        'epr.purchase.request.line',
        'request_id',
        string='Products'
    )
    estimated_total = fields.Monetary(
        string='Estimated Total',
        compute='_compute_estimated_total',
        store=True,
        currency_field='currency_id'
    )

    # ==========================================================================
    # LOG FIELDS
    # ==========================================================================
    date_approved = fields.Datetime(
        string='Approved Date',
        readonly=True,
        copy=False,
        help="Ngày được phê duyệt."
    )

    approved_by_id = fields.Many2one(
        comodel_name='res.users',
        string='Approved By',
        readonly=True,
        copy=False,
        help="Người đã phê duyệt."
    )

    date_submitted = fields.Datetime(
        string='Submitted Date',
        readonly=True,
        copy=False
    )

    # ==========================================================================
    # MODEL METHODS
    # ==========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('epr.purchase.request') or _('New')
        return super().create(vals_list)

    # Compute estimated total
    @api.depends('line_ids.subtotal_estimated', 'currency_id')
    def _compute_estimated_total(self):
        """Tính tổng tiền dự kiến từ các dòng chi tiết"""
        for request in self:
            # Sử dụng sum() trên danh sách mapped là đúng, nhưng cần cẩn thận nếu line khác tiền tệ
            # Ở đây giả định line dùng chung currency với header
            total = sum(line.subtotal_estimated for line in request.line_ids)
            request.estimated_total = total

    # Compute approvers
    # @api.depends('employee_id', 'department_id', 'estimated_total')
    # def _compute_approvers(self):
    #     # Placeholder for approval matrix logic
    #     for request in self:
    #         # For now, set line manager as approver
    #         if request.employee_id and request.employee_id.parent_id:
    #             request.approver_ids = [
    #                 (6, 0, [request.employee_id.parent_id.user_id.id])
    #             ]
    #         else:
    #             request.approver_ids = False

    # ==========================================================================
    # HELPER METHODS (Tách logic tìm người duyệt ra riêng)
    # ==========================================================================

    def _get_applicable_approvers(self):
        """
        Hàm logic xác định ai là người duyệt.
        Tách ra để dễ tái sử dụng hoặc override sau này
        (ví dụ thêm Matrix duyệt theo số tiền).
        """
        self.ensure_one()
        approvers = self.env['res.users']

        # Logic 1: Line Manager (Trưởng bộ phận)
        if self.employee_id and self.employee_id.parent_id and self.employee_id.parent_id.user_id:
            approvers |= self.employee_id.parent_id.user_id

        # Logic 2 (Ví dụ): Nếu tiền > 50tr thì cần thêm Giám đốc (Code ví dụ)
        # if self.estimated_total > 50000000:
        #     director = ... 
        #     approvers |= director

        return approvers

    # ==========================================================================
    # BUSINESS ACTIONS
    # ==========================================================================

    # Submit PR for approval
    def action_submit(self):
        """Submit PR for approval"""
        self.ensure_one()

        # 1. Validate dữ liệu đầu vào
        if not self.line_ids:
            raise ValidationError(_('Cannot submit an empty purchase request. Please add at least one product line.'))

        # 2. Tính toán và Gán người duyệt (Freeze approvers list)
        # Thay vì dùng compute field, ta gán trực tiếp lúc submit để "chốt" người duyệt
        required_approvers = self._get_applicable_approvers()

        if not required_approvers:
            raise ValidationError(_('No approver found (Line Manager). Please contact HR or Admin to update your employee profile.'))

        self.write({
            'approver_ids': [(6, 0, required_approvers.ids)],
            'state': 'to_approve',
            'date_submitted': fields.Datetime.now()
        })

        # # 3. Tạo Activity (To-Do) cho người duyệt để họ nhận thông báo
        # NOTE: Commented out for testing without mail server
        # for approver in self.approver_ids:
        #     self.activity_schedule(
        #         'mail.mail_activity_data_todo',
        #         user_id=approver.id,
        #         summary=_('Purchase Request Approval Required'),
        #         note=_(
        #             'Purchase Request %s requires your approval.\n'
        #             'Total Amount: %s %s'
        #         ) % (
        #             self.name,
        #             self.estimated_total,
        #             self.currency_id.symbol
        #         )
        #     )

        # Post message to chatter
        # self.message_post(
        #     body=_('Purchase Request submitted for approval to: %s') % (
        #         ', '.join(self.approver_ids.mapped('name'))
        #     )
        # )

    # Approver action: Approve PR
    def action_approve(self):
        """Approve PR"""
        self.ensure_one()

        # 1. Check quyền: User hiện tại có nằm trong danh sách được duyệt không?
        # Cho phép Administrator bypass
        if not self.env.is_superuser() and self.env.user not in self.approver_ids:
            raise UserError(_('You are not authorized to approve this request.'))

        # 2. Cập nhật trạng thái
        self.write({
            'state': 'approved',
            # Lưu lại ngày và người duyệt để audit sau này
            'date_approved': fields.Datetime.now(),
            'approved_by_id': self.env.user.id
        })

        # Mark activities as done
        # NOTE: Commented out for testing without mail server
        # self.activity_ids.filtered(
        #     lambda a: a.user_id == self.env.user
        # ).action_feedback(feedback='Approved')

        # Post message to chatter
        # self.message_post(
        #     body=_('Purchase Request approved by %s') % (
        #         self.env.user.name
        #     )
        # )

    # Hàm mở Wizard
    def action_reject_wizard(self):
        """Open rejection wizard"""
        self.ensure_one()
        return {
            'name': _('Reject Purchase Request'),
            'type': 'ir.actions.act_window',
            'res_model': 'epr.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            # Truyền ID hiện tại vào context để wizard tự động nhận diện
            'context': {'default_request_id': self.id}
        }

    # Approver action: Reject PR
    def action_reject(self, reason):
        """
        Reject PR with reason (called from wizard).
        Chuyển trạng thái sang 'draft' và ghi log.
        """
        self.ensure_one()

        # Check quyền: User hiện tại có nằm trong danh sách được duyệt không?
        # Lưu ý: Nên cho phép cả Administrator bypass check này để xử lý sự cố
        if not self.env.is_superuser() and self.env.user not in self.approver_ids:
            raise UserError(
                _('You are not authorized to reject this request.')
            )

        # Thực hiện ghi dữ liệu
        self.write({
            'state': 'draft',
            'rejection_reason': reason,
            'approver_ids': [(5, 0, 0)]  # QUAN TRỌNG: Xóa sạch người duyệt để clear danh sách chờ
        })

        # Mark activities as done
        # NOTE: Commented out for testing without mail server
        # self.activity_ids.filtered(
        #     lambda a: a.user_id == self.env.user
        # ).action_feedback(feedback='Rejected')

        # Post message to chatter
        # self.message_post(
        #     body=_('Purchase Request rejected by %s\nReason: %s') % (
        #         self.env.user.name,
        #         reason
        #     )
        # )

    # User action: Reset to draft when accidentally submitted
    def action_reset_to_draft(self):
        """
        Reset PR back to draft state.
        Cho phép User sửa lại phiếu khi submit nhầm hoặc sau khi bị reject.
        Chỉ owner mới được reset (không phải Manager).
        """
        self.ensure_one()

        # Validation 1: Check state
        if self.state not in ['to_approve', 'rejected']:
            raise UserError(_(
                'You can only reset PR when it is in "To Approve" '
                'or "Rejected" state.'
            ))

        # Validation 2: Check permission - Only owner can reset
        # Admin có thể bypass
        if (not self.env.is_superuser() and
                self.employee_id.user_id != self.env.user):
            raise UserError(_(
                'Only the requester (%s) can reset this PR to draft.'
            ) % self.employee_id.name)

        # Reset state và clear data
        self.write({
            'state': 'draft',
            'approver_ids': [(5, 0, 0)],  # Clear approvers list
            'rejection_reason': False,  # Clear rejection reason
            'date_submitted': False,  # Clear submission date
        })

        # Post message for audit trail
        # NOTE: Commented out for testing without mail server
        # self.message_post(
        #     body=_(
        #         'Purchase Request reset to Draft by %s for editing.'
        #     ) % self.env.user.name
        # )

        # Cancel pending activities
        # NOTE: Commented out for testing without mail server
        # self.activity_ids.unlink()


class EprPurchaseRequestLine(models.Model):
    """
    Chi tiết dòng yêu cầu mua sắm.
    Thiết kế theo hướng Free-text để thuận tiện cho người yêu cầu (Staff).
    """
    _name = 'epr.purchase.request.line'
    _description = 'Chi tiết yêu cầu mua sắm'

    # ==========================================================================
    # RELATIONAL FIELDS
    # ==========================================================================

    request_id = fields.Many2one(
        comodel_name='epr.purchase.request',
        string='Purchase Request',
        required=True,
        ondelete='cascade',  # Xóa PR cha sẽ xóa luôn các dòng con
        index=True,
        help="Liên kết đến phiếu yêu cầu mua sắm gốc."
    )

    # Lấy tiền tệ từ phiếu cha để tính toán giá trị.
    # store=True để hỗ trợ tìm kiếm và báo cáo nhanh hơn.
    currency_id = fields.Many2one(
        related='request_id.currency_id',
        string='Currency',
        store=True,
        readonly=True,
        help="Tiền tệ được kế thừa từ phiếu yêu cầu chính."
    )

    # Trường này để Purchasing Staff map sau khi duyệt. Staff không cần thấy.
    product_id = fields.Many2one(
        comodel_name='product.product',
        string='Product',
        domain=[('purchase_ok', '=', True)],  # Chỉ chọn các sản phẩm được phép mua
        help="Trường dành cho bộ phận thu mua map với kho."
    )

    # product_uom_id = fields.Many2one(
    #     comodel_name='uom.uom',
    #     string='Unit of Measure',
    #     domain="[('category_id', '=', product_uom_category_id)]",
    #     help="Đơn vị tính của sản phẩm. Tự động điền nếu chọn sản phẩm."
    # )

    # Đơn vị tính dạng text tự nhập (VD: Cái, Hộp, Giờ, Lô...) 
    # Tránh bắt Staff phải chọn UoM phức tạp của hệ thống
    uom_name = fields.Char(
        string='Unit of Measure',
        default='Unit',
        required=True
    )

    # ==========================================================================
    # DATA FIELDS
    # ==========================================================================

    # Dùng trường này làm tên hiển thị (rec_name)
    # Staff sẽ nhập ngắn gọn: VD "Laptop Dell XPS 13"
    name = fields.Char(
        string='Product Name', 
        required=True,
        help="Nhập tên ngắn gọn của hàng hóa cần mua."
    )

    # Dùng HTML để Staff có thể copy/paste hình ảnh, link, format màu sắc từ web
    product_description = fields.Html(
        string='Product Description',
        required=True,
        help="Mô tả chi tiết, có thể dán link, hình ảnh minh họa, thông số kỹ thuật..."
    )

    # Dùng Char hoặc Text cho tên nhà cung cấp gợi ý (Staff không cần chọn trong danh bạ đối tác)
    vendor_name = fields.Char(
        string='Vendor Name',
        help="Tên nhà cung cấp được đề xuất bởi người yêu cầu (tham khảo)."
    )

    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        digits='Product Unit of Measure', # Sử dụng độ chính xác cấu hình trong hệ thống
        required=True,
        help="Số lượng cần mua."
    )

    estimated_price = fields.Monetary(
        string='Estimated Unit Price',
        currency_field='currency_id',
        help="Đơn giá ước tính tại thời điểm yêu cầu."
    )

    subtotal_estimated = fields.Monetary(
        string='Estimated Subtotal',
        compute='_compute_subtotal_estimated',
        store=True,
        currency_field='currency_id',
        help="Tổng tiền ước tính (Số lượng * Đơn giá)."
    )

    # ==========================================================================
    # COMPUTE FIELDS
    # ==========================================================================

    @api.depends('quantity', 'estimated_price')
    def _compute_subtotal_estimated(self):
        for line in self:
            # Đảm bảo giá trị là số (0.0) nếu người dùng chưa nhập
            qty = line.quantity or 0.0
            price = line.estimated_price or 0.0
            line.subtotal_estimated = qty * price

    # === logic Onchange ===
    # Chỉ chạy khi Purchasing Staff chọn product_id (lúc xử lý phiếu)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if not self.product_id:
            return

        # Đơn vị tính (UoM): NÊN ghi đè theo chuẩn hệ thống
        # Lý do: Staff có thể nhập "Cái", nhưng hệ thống kho quản lý là "Unit(s)".
        # Để tạo PO chính xác sau này, ta cần lấy UoM chuẩn của sản phẩm.
        self.uom_name = self.product_id.uom_po_id.name or self.product_id.uom_id.name

        # Giá dự kiến: Chỉ điền nếu Staff để bằng 0
        if self.estimated_price == 0.0:
            self.estimated_price = self.product_id.standard_price

        # Tên sản phẩm: KHÔNG ghi đè (Giữ nguyên mô tả của Staff)
        # Vì Staff mô tả nhu cầu thực tế (VD: "Máy tính Dell cho kế toán"), 
        # còn tên Product hệ thống có thể chung chung (VD: "Laptop Dell Latitude").
        # Ta chỉ điền nếu dòng này do Purchasing tạo mới hoàn toàn (name đang rỗng).
        if not self.name:
            self.name = self.product_id.display_name
