from odoo import models, fields, api
from datetime import datetime

class PosAdminRapport(models.Model):
    _name = 'pos.admin.rapport'
    _description = 'Rapport Administration POS'

    date_debut = fields.Date('Du')
    date_fin = fields.Date('Au')

    ca_total = fields.Float('CA Total', compute='_compute_metrics', store=False)
    ca_cash = fields.Float('CA Cash', compute='_compute_metrics', store=False)
    ca_bp = fields.Float('CA BP', compute='_compute_metrics', store=False)
    nb_commandes = fields.Integer('Nb commandes', compute='_compute_metrics', store=False)

    entrees = fields.Float('Entrées de caisse', compute='_compute_metrics', store=False)
    depenses = fields.Float('Sorties de caisse', compute='_compute_metrics', store=False)
    resultat = fields.Float('Résultat (Entrées - Sorties)', compute='_compute_metrics', store=False)

    nb_livraisons = fields.Integer('Nb livraisons', compute='_compute_metrics', store=False)
    montant_livre_total = fields.Float('Montant livré', compute='_compute_metrics', store=False)
    sacs_sortis = fields.Float('Sacs sortis (livraisons + sorties)', compute='_compute_metrics', store=False)
    kg_sortis = fields.Float('Kg sortis (livraisons + sorties)', compute='_compute_metrics', store=False)

    @api.depends('date_debut', 'date_fin')
    def _compute_metrics(self):
        Cmd = self.env['pos.caisse.commande']
        Mvt = self.env['pos.caisse.mouvement']
        Liv = self.env['pos.livraison.livraison']
        Sortie = self.env['pos.livraison.sortie.stock']
        poids_sac = float(self.env['ir.config_parameter'].sudo().get_param('pos_livraison.poids_sac', 50))
        for rec in self:
            # Period bounds
            domain_date_cmd = []
            domain_date_mvt = []
            domain_date_liv = []
            domain_date_sortie = []
            if rec.date_debut:
                start_dt = datetime.combine(rec.date_debut, datetime.min.time())
                s = fields.Datetime.to_string(start_dt)
                domain_date_cmd.append(('date', '>=', s))
                domain_date_mvt.append(('date', '>=', s))
                domain_date_liv.append(('date', '>=', s))
                domain_date_sortie.append(('date', '>=', s))
            if rec.date_fin:
                end_dt = datetime.combine(rec.date_fin, datetime.max.time())
                e = fields.Datetime.to_string(end_dt)
                domain_date_cmd.append(('date', '<=', e))
                domain_date_mvt.append(('date', '<=', e))
                domain_date_liv.append(('date', '<=', e))
                domain_date_sortie.append(('date', '<=', e))

            # Commandes
            domain_cmd = [('state', '!=', 'annule')] + domain_date_cmd
            commandes = Cmd.search(domain_cmd)
            rec.nb_commandes = len(commandes)
            rec.ca_total = sum(commandes.mapped('total')) if commandes else 0.0
            rec.ca_bp = sum(commandes.filtered(lambda c: c.type_paiement == 'bp').mapped('total')) if commandes else 0.0
            rec.ca_cash = rec.ca_total - rec.ca_bp

            # Mouvements de caisse
            domain_mvt = domain_date_mvt
            mvt_entree = Mvt.search([('type', '=', 'entree')] + domain_mvt)
            mvt_sortie = Mvt.search([('type', '=', 'sortie')] + domain_mvt)
            rec.entrees = sum(mvt_entree.mapped('montant')) if mvt_entree else 0.0
            rec.depenses = sum(mvt_sortie.mapped('montant')) if mvt_sortie else 0.0
            rec.resultat = rec.entrees - rec.depenses

            # Livraisons et sorties de stock
            livraisons = Liv.search(domain_date_liv)
            sorties = Sortie.search(domain_date_sortie)
            rec.nb_livraisons = len(livraisons)
            rec.montant_livre_total = sum(livraisons.mapped('montant_livre')) if livraisons else 0.0
            sacs_liv = sum(livraisons.mapped('sacs_farine')) if livraisons else 0.0
            sacs_sortie = sum(sorties.mapped('quantite_sacs')) if sorties else 0.0
            rec.sacs_sortis = sacs_liv + sacs_sortie
            rec.kg_sortis = rec.sacs_sortis * poids_sac

class SortieStock(models.Model):
    _inherit = 'pos.livraison.sortie.stock'

    validated = fields.Boolean('Validée', default=False, copy=False, index=True)
    validated_by = fields.Many2one('res.users', string='Validée par', readonly=True)
    validated_at = fields.Datetime('Validée le', readonly=True)

    def action_valider(self):
        for rec in self:
            if not rec.validated:
                rec.write({
                    'validated': True,
                    'validated_by': self.env.user.id,
                    'validated_at': fields.Datetime.now(),
                })
