# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError


class EprCreateRfqWizard(models.TransientModel):
    _name = 'epr.create.rfq.wizard'
    _description = 'Wizard: Merge PRs to RFQ'

    # Danh sách các dòng PR đang được xử lý trong Wizard
    line_ids = fields.One2many(
        comodel_name='epr.create.rfq.line',
        inverse_name='wizard_id',
        string='PR Lines to Process'
    )

    @api.model
    def default_get(self, fields_list):
        """
        Khi mở Wizard, tự động load các PR đã chọn từ màn hình danh sách.
        """
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])

        if not active_ids:
            return res

        # Lấy danh sách PR gốc
        requests = self.env['epr.purchase.request'].browse(active_ids)

        # Prepare dữ liệu cho dòng Wizard
        lines_vals = []
        for pr in requests:
            # Chỉ xử lý các PR đã được duyệt (Ví dụ trạng thái 'approved')
            # Bạn có thể bỏ comment dòng dưới nếu có field state
            if pr.state != 'approved':
                raise UserError(_("PR %s chưa được duyệt.", pr.name))

            for line in pr.line_ids:
                lines_vals.append(Command.create({
                    'pr_line_id': line.id,  # Link tới PR Line
                    'request_id': pr.id,
                    'final_vendor_id': line.final_vendor_id.id if line.final_vendor_id else False,
                    'suggested_vendor_name': line.suggested_vendor_name,
                }))

        res['line_ids'] = lines_vals
        return res

    def action_create_rfqs(self):
        """
        Logic hardened with .sudo():
        1. Access PR data using sudo to bypass security rules.
        2. Group by Vendor.
        3. Create RFQ Header and Lines using sudo() to ensure data persistence.
        4. Redirect to the newly created RFQ(s).
        """
        self.ensure_one()

        # 1. Validation
        missing_vendor_lines = self.line_ids.filtered(lambda l: not l.final_vendor_id)
        if missing_vendor_lines:
            raise UserError(_("Please select a Final Vendor for all lines."))

        missing_product_lines = self.line_ids.filtered(lambda l: not l.final_product_id)
        if missing_product_lines:
            raise UserError(_("Please select a Final Product for all lines."))

        # 2. Grouping
        grouped_lines = {}
        for wiz_line in self.line_ids:
            # Sync back to PR line (Sudo to ensure write permission if needed)
            if wiz_line.pr_line_id.final_vendor_id != wiz_line.final_vendor_id:
                wiz_line.pr_line_id.sudo().write({'final_vendor_id': wiz_line.final_vendor_id.id})
            
            vendor = wiz_line.final_vendor_id
            if vendor not in grouped_lines:
                grouped_lines[vendor] = self.env['epr.create.rfq.line']
            grouped_lines[vendor] |= wiz_line

        created_rfqs = self.env['epr.rfq'].sudo()

        # 3. RFQ Creation
        for vendor, wiz_lines in grouped_lines.items():
            rfq_line_commands = []
            source_pr_ids = []

            for wiz_line in wiz_lines:
                # DÙNG SUDO: Để chắc chắn lấy được dữ liệu PR line
                pr_line_sudo = wiz_line.pr_line_id.sudo()
                request_sudo = wiz_line.request_id.sudo()
                
                # Collect unique source PR ids
                if request_sudo and request_sudo.id not in source_pr_ids:
                    source_pr_ids.append(request_sudo.id)

                # Determine UoM (Directly from Product or PR Line)
                uom_id = False
                if wiz_line.final_product_id:
                    uom_id = wiz_line.final_product_id.uom_po_id.id or wiz_line.final_product_id.uom_id.id
                
                if not uom_id and pr_line_sudo.product_id:
                    uom_id = pr_line_sudo.product_id.uom_po_id.id or pr_line_sudo.product_id.uom_id.id

                # Create line command - DÙNG GIÁ TRỊ TỪ SUDO RECORD
                rfq_line_commands.append(Command.create({
                    'product_id': wiz_line.final_product_id.id,
                    'description': pr_line_sudo.name or '',
                    'quantity': pr_line_sudo.quantity or 1.0,
                    'uom_id': uom_id,
                    'price_unit': 0.0,
                }))

            # Create RFQ header - SỬ DỤNG SUDO ĐỂ TẠO
            rfq = self.env['epr.rfq'].sudo().create({
                'partner_id': vendor.id,
                'state': 'draft',
                'date_order': fields.Datetime.now(),
                'request_ids': [Command.set(source_pr_ids)],
                'line_ids': rfq_line_commands,
            })
            created_rfqs |= rfq

        # 4. Result Action
        if len(created_rfqs) == 1:
            return {
                'name': _('Request for Quotation'),
                'type': 'ir.actions.act_window',
                'res_model': 'epr.rfq',
                'view_mode': 'form',
                'res_id': created_rfqs.id,
                'target': 'current',
            }
        else:
            return {
                'name': _('Requests for Quotation'),
                'type': 'ir.actions.act_window',
                'res_model': 'epr.rfq',
                'view_mode': 'list,form',
                'domain': [('id', 'in', created_rfqs.ids)],
                'target': 'current',
            }


class EprCreateRfqLine(models.TransientModel):
    _name = 'epr.create.rfq.line'
    _description = 'Wizard Line: PR Details'

    wizard_id = fields.Many2one('epr.create.rfq.wizard', string='Wizard')

    # Link tới PR gốc (Readonly)
    request_id = fields.Many2one(
        comodel_name='epr.purchase.request',
        string='Purchase Request',
        readonly=True
    )

    # Link tới PR Line gốc
    pr_line_id = fields.Many2one(
        comodel_name='epr.purchase.request.line',
        string='PR Line',
        readonly=True
    )

    # Cột hiển thị text gợi ý (Readonly) -> Giúp Officer tham chiếu
    suggested_vendor_name = fields.Char(
        string='Suggested Vendor (Text)',
        readonly=True,
        help="Tên nhà cung cấp do người yêu cầu nhập tay (tham khảo)."
    )

    # Cột Final Vendor (Editable) -> Đây là nơi Officer thao tác chính
    final_vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Final Vendor',
        required=True,
        # domain="[('supplier_rank', '>', 0)]",  # Chỉ lấy nhà cung cấp
        help="Chọn nhà cung cấp chính thức trong hệ thống để tạo RFQ."
    )

    # Lấy thông tin sản phẩm cần mua
    product_description = fields.Char(
        related='pr_line_id.name',
        string='Product / Description',
        readonly=True
    )

    # Purchasing Officer chọn sản phẩm tương ứng với mô tả của User
    final_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Final Product',
        required=True,
        # domain="[('purchase_ok', '=', True)]",
        help="Chọn sản phẩm tương ứng với mô tả của người yêu cầu."
    )

    # Lấy số lượng
    quantity = fields.Float(
        related='pr_line_id.quantity',
        string='Qty',
        readonly=True
    )

    # Lấy đơn vị tính
    uom_name = fields.Char(
        related='pr_line_id.uom_name',
        string='UoM',
        readonly=True
    )
