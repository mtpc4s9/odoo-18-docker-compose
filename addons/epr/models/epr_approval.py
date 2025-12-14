# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


# ==============================================================================
# MODEL CẤU HÌNH (TEMPLATE)
# Admin thiết lập: Tại bước (Sequence) này, ai cần duyệt và duyệt theo kiểu gì?
# ==============================================================================
class EprApprovalConfig(models.Model):
    _name = 'epr.approval.config'
    _description = 'EPR Approval Configuration'
    _order = 'sequence, min_amount'

    name = fields.Char(
        string='Rule Name', 
        required=True, 
        translate=True
    )

    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company
    )

    # 1. Điều kiện kích hoạt
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        required=True,
        help="Thứ tự thực hiện. Các Rule cùng Sequence sẽ chạy song song."
    )

    min_amount = fields.Monetary(
        string='Minimum Amount',
        currency_field='currency_id',
        default=0.0,
        help="Rule này chỉ áp dụng nếu tổng tiền RFQ lớn hơn số này."
    )

    currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    # 2. Ai duyệt?
    user_ids = fields.Many2many(
        comodel_name='res.users',
        string='Approvers',
        required=True,
        domain="[('share', '=', False)]",  # Chỉ lấy user nội bộ
        help="Danh sách những người có quyền duyệt rule này."
    )

    # 3. Logic duyệt: 1 người hay tất cả?
    approval_type = fields.Selection(
        selection=[
            ('any', 'Any Approver (One pass)'),
            ('all', 'All Approvers (Everyone must sign)')
        ],
        string='Approval Type',
        default='any',
        required=True
    )


# ==============================================================================
# MODEL VẬN HÀNH (INSTANCE)
# Sinh ra khi RFQ -> 'to_approve'. 
# Đây là snapshot của Config tại thời điểm submit.
# ==============================================================================
class EprApprovalEntry(models.Model):
    _name = 'epr.approval.entry'
    _description = 'RFQ Approval Entry'
    _order = 'sequence, id'

    # Link về RFQ
    rfq_id = fields.Many2one(
        comodel_name='epr.rfq',
        string='RFQ Reference',
        required=True,
        ondelete='cascade'
    )

    config_id = fields.Many2one(
        comodel_name='epr.approval.config',
        string='Source Rule',
        readonly=True,
        ondelete='set null'  # Giữ entry dù config bị xóa
    )

    # Thông tin snapshot từ Config
    name = fields.Char(
        string='Summary',
        required=True
    )

    sequence = fields.Integer(
        string='Sequence',
        required=True
    )

    approval_type = fields.Selection(
        selection=[
            ('any', 'Any'),
            ('all', 'All')
        ],
        required=True
    )

    # Trạng thái dòng duyệt này
    status = fields.Selection(
        selection=[
            ('new', 'To Process'),      # Chưa đến lượt (do sequence cao hơn)
            ('pending', 'Pending'),     # Đang chờ duyệt
            ('approved', 'Approved'),   # Đã xong
            ('rejected', 'Rejected')    # Bị từ chối
        ],
        string='Status',
        default='new',
        index=True,
        readonly=True
    )

    # Danh sách người CẦN duyệt
    required_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='epr_approval_req_users_rel',
        string='Required Approvers',
        readonly=True
    )

    # Danh sách người ĐÃ duyệt (quan trọng cho logic 'All')
    actual_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='epr_approval_act_users_rel',
        string='Approved By',
        readonly=True
    )

    approval_date = fields.Datetime(
        string='Last Action Date',
        readonly=True
    )

    # Field hỗ trợ UI: User hiện tại có được nút Approve không?
    can_approve = fields.Boolean(compute='_compute_can_approve')

    @api.depends('status', 'required_user_ids', 'actual_user_ids', 'approval_type')
    @api.depends_context('uid')
    def _compute_can_approve(self):
        current_user = self.env.user
        for record in self:
            # 1. Phải đang ở trạng thái Pending
            if record.status != 'pending':
                record.can_approve = False
                continue

            # 2. User phải nằm trong danh sách được phép
            if current_user not in record.required_user_ids:
                record.can_approve = False
                continue

            # 3. Nếu là 'All', user này chưa được duyệt trước đó
            if record.approval_type == 'all' and current_user in record.actual_user_ids:
                record.can_approve = False
            else:
                record.can_approve = True

    # -------------------------------------------------------------------------
    # ACTION METHODS
    # -------------------------------------------------------------------------
    def action_approve_line(self):
        """User bấm nút Approve trên dòng này"""
        self.ensure_one()
        if not self.can_approve:
            raise UserError(_("You either don't have permission to approve or you've already approved it."))

        # Ghi nhận người duyệt
        self.write({
            'actual_user_ids': [(4, self.env.user.id)],
            'approval_date': fields.Datetime.now()
        })

        # Kiểm tra điều kiện hoàn thành dòng này
        is_done = False
        if self.approval_type == 'any':
            # Chỉ cần 1 người -> Done
            is_done = True
        elif self.approval_type == 'all':
            # Phải đủ tất cả required users
            # Dùng set để so sánh ID cho nhanh
            required_set = set(self.required_user_ids.ids)
            actual_set = set(self.actual_user_ids.ids)
            if required_set.issubset(actual_set):
                is_done = True

        if is_done:
            self.status = 'approved'
            # Gọi về RFQ cha để check xem có mở tiếp tầng sau (Sequence kế) không?
            self.rfq_id._check_approval_progression()

    def action_refuse_line(self):
        """User từ chối -> Từ chối TOÀN BỘ RFQ"""
        self.ensure_one()
        if not self.can_approve:
            raise UserError(_("You don't have permission to reject this RFQ."))

        self.write({
            'status': 'rejected',
            'approval_date': fields.Datetime.now()
        })

        # Đẩy RFQ về trạng thái 'rejected' hoặc 'cancel'
        # Gọi hàm xử lý từ chối bên RFQ
        self.rfq_id.action_reject_approval()
