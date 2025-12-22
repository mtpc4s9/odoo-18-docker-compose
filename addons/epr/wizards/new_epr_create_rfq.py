# -*- coding: utf-8 -*-
from odoo import models, fields, api, Command, _
from odoo.exceptions import UserError

class EprCreateRfqWizard(models.TransientModel):
    _name = 'epr.create.rfq.wizard'
    _description = 'Wizard: Merge PRs to RFQ'

    line_ids = fields.One2many('epr.create.rfq.line', 'wizard_id', string='Lines')

    @api.model
    def default_get(self, fields_list):
        """
        Load dữ liệu từ PRs được chọn vào Wizard để User review trước khi tạo RFQ.
        """
        res = super().default_get(fields_list)
        active_ids = self.env.context.get('active_ids', [])
        
        if not active_ids:
            return res

        # Lấy các Purchase Requests được chọn
        requests = self.env['epr.purchase.request'].browse(active_ids)
        
        lines_vals = []
        for pr in requests:
            # Giả định PR có field line_ids chứa sản phẩm chi tiết
            # Ta cần loop qua từng dòng PR để đưa vào Wizard
            for pr_line in pr.line_ids:
                lines_vals.append(Command.create({
                    'request_id': pr.id,                 # Link để truy vết PR gốc
                    'pr_line_id': pr_line.id,            # Link dòng gốc
                    'suggested_vendor_name': pr.suggested_vendor_name, # Hoặc pr_line.suggested_vendor
                    'final_vendor_id': pr.final_vendor_id.id,
                    'final_product_id': pr_line.product_id.id,
                    'product_description': pr_line.name or pr_line.product_id.name,
                    'quantity': pr_line.quantity,        # <--- QUAN TRỌNG: Lấy số lượng từ PR
                    'uom_name': pr_line.uom_id.name,     # Chỉ để hiển thị
                }))

        res['line_ids'] = lines_vals
        return res

    def action_create_rfqs(self):
        self.ensure_one()
        
        # 1. Validate: Kiểm tra xem đã chọn Vendor chưa
        if any(not l.final_vendor_id for l in self.line_ids):
            raise UserError(_("Vui lòng chọn 'Final Vendor' cho tất cả các dòng trước khi tạo RFQ."))

        # 2. Gom nhóm theo Vendor (Dictionary: {vendor_id: [lines]})
        grouped_by_vendor = {}
        for line in self.line_ids:
            vendor = line.final_vendor_id
            if vendor not in grouped_by_vendor:
                grouped_by_vendor[vendor] = []
            grouped_by_vendor[vendor].append(line)

        new_rfqs = self.env['epr.rfq']

        # 3. Tạo RFQ cho từng Vendor
        for vendor, w_lines in grouped_by_vendor.items():
            
            # A. Thu thập tất cả Source Requests (Many2many) cho RFQ Header
            # Dùng set() để loại bỏ các ID trùng lặp nếu nhiều dòng cùng thuộc 1 PR
            source_request_ids = list(set(l.request_id.id for l in w_lines))

            # B. Chuẩn bị dữ liệu line cho RFQ (One2many)
            rfq_lines_commands = []
            for w_line in w_lines:
                rfq_lines_commands.append(Command.create({
                    'product_id': w_line.final_product_id.id,
                    'description': w_line.product_description,
                    'quantity': w_line.quantity,         # <--- FIX LỖI: Map đúng số lượng
                    # 'uom_id': ...,                     # Nếu bạn có field uom_id
                    # 'price_unit': 0.0,                 # RFQ thường để giá 0 để xin báo giá
                }))

            # C. Tạo RFQ (Header + Lines)
            # Dùng .sudo() nếu user hiện tại không có quyền tạo RFQ nhưng được phép chạy wizard này
            rfq_vals = {
                'vendor_id': vendor.id,
                'state': 'draft',
                'date_order': fields.Datetime.now(),
                
                # FIX LỖI: Dùng Command.set() để gán danh sách IDs vào Many2many
                'request_ids': [Command.set(source_request_ids)], 
                
                # Tạo các dòng con
                'line_ids': rfq_lines_commands, 
            }
            
            new_rfq = self.env['epr.rfq'].sudo().create(rfq_vals)
            new_rfqs += new_rfq

        # 4. Redirect người dùng đến (các) RFQ vừa tạo
        if not new_rfqs:
            return {'type': 'ir.actions.act_window_close'}
            
        action = {
            'name': _('Generated RFQs'),
            'type': 'ir.actions.act_window',
            'res_model': 'epr.rfq',
            'domain': [('id', 'in', new_rfqs.ids)],
            'context': {'create': False},
        }
        if len(new_rfqs) == 1:
            action.update({
                'view_mode': 'form',
                'res_id': new_rfqs.id,
            })
        else:
            action.update({
                'view_mode': 'list,form', # Odoo 18 dùng 'list'
            })
            
        return action


class EprCreateRfqLine(models.TransientModel):
    _name = 'epr.create.rfq.line'
    _description = 'Wizard Line: PR Details'
    
    wizard_id = fields.Many2one('epr.create.rfq.wizard')
    
    # Các field dữ liệu để chuyển từ PR -> RFQ
    request_id = fields.Many2one('epr.purchase.request', readonly=True)
    pr_line_id = fields.Many2one('epr.purchase.request.line', readonly=True) # Lưu tham chiếu dòng gốc
    
    suggested_vendor_name = fields.Char(readonly=True)
    final_vendor_id = fields.Many2one('res.partner', string='Final Vendor', required=True)
    
    final_product_id = fields.Many2one('product.product', string='Product', required=True)
    product_description = fields.Char(string='Description')
    
    # Field Quantity cần editable trong wizard để user có thể điều chỉnh nếu muốn
    quantity = fields.Float(string='Quantity', digits='Product Unit of Measure') 
    uom_name = fields.Char(readonly=True)
