from odoo import http, fields
from odoo.http import request
from datetime import datetime

class PosAdminApi(http.Controller):
    @http.route('/api/pos_admin/rapports', type='json', auth='user', methods=['POST'], csrf=False)

    def get_rapports(self, **payload):
        params = http.request.jsonrequest or payload
        payload = params
        date_debut = payload.get('date_debut')
        date_fin = payload.get('date_fin')
        try:
            start_dt = datetime.combine(fields.Date.from_string(date_debut), datetime.min.time()) if date_debut else None
            end_dt = datetime.combine(fields.Date.from_string(date_fin), datetime.max.time()) if date_fin else None
        except Exception:
            return {'status': 'error', 'message': 'Format de date invalide (YYYY-MM-DD attendu)'}
        Cmd = request.env['pos.caisse.commande'].sudo()
        Mvt = request.env['pos.caisse.mouvement'].sudo()
        Liv = request.env['pos.livraison.livraison'].sudo()
        Sortie = request.env['pos.livraison.sortie.stock'].sudo()
        # Build date domains
        def date_domain(field):
            dom = []
            if start_dt:
                dom.append((field, '>=', fields.Datetime.to_string(start_dt)))
            if end_dt:
                dom.append((field, '<=', fields.Datetime.to_string(end_dt)))
            return dom
        # Commandes
        commandes = Cmd.search([('state', '!=', 'annule')] + date_domain('date'))
        ca_total = sum(commandes.mapped('total')) if commandes else 0.0
        ca_bp = sum(commandes.filtered(lambda c: c.type_paiement == 'bp').mapped('total')) if commandes else 0.0
        ca_cash = ca_total - ca_bp
        nb_commandes = len(commandes)
        # Mouvements
        mvt_entree = Mvt.search([('type', '=', 'entree')] + date_domain('date'))
        mvt_sortie = Mvt.search([('type', '=', 'sortie')] + date_domain('date'))
        entrees = sum(mvt_entree.mapped('montant')) if mvt_entree else 0.0
        depenses = sum(mvt_sortie.mapped('montant')) if mvt_sortie else 0.0
        resultat = entrees - depenses
        # Livraisons
        livraisons = Liv.search(date_domain('date'))
        nb_livraisons = len(livraisons)
        montant_livre_total = sum(livraisons.mapped('montant_livre')) if livraisons else 0.0
        sacs_liv = sum(livraisons.mapped('sacs_farine')) if livraisons else 0.0
        # Sorties de stock (toutes)
        sorties = Sortie.search(date_domain('date'))
        sacs_sortie = sum(sorties.mapped('quantite_sacs')) if sorties else 0.0
        montant_sorties = sum(sorties.mapped('montant')) if sorties else 0.0
        poids_sac = float(request.env['ir.config_parameter'].sudo().get_param('pos_livraison.poids_sac', 50))
        sacs_sortis = sacs_liv
        kg_sortis = sacs_sortis * poids_sac
        return {
            'status': 'success',
            'date_debut': date_debut,
            'date_fin': date_fin,
            'ca_total': ca_total,
            'ca_cash': ca_cash,
            'ca_bp': ca_bp,
            'nb_commandes': nb_commandes,
            'entrees': entrees,
            'depenses': depenses,
            'resultat': resultat,
            'nb_livraisons': nb_livraisons,
            'montant_livre_total': montant_livre_total,
            'sacs_sortis': sacs_sortis,
            'sortie_stocks': sacs_sortie,
            'montant_sorties': montant_sorties,
            'kg_sortis': kg_sortis,
        }

    @http.route('/api/pos_admin/sorties_a_valider', type='json', auth='user', methods=['GET', 'POST'], csrf=False)
    def sorties_a_valider(self, **payload):
        payload = payload or {}
        date_debut = payload.get('date_debut')
        date_fin = payload.get('date_fin')
        try:
            start_dt = datetime.combine(fields.Date.from_string(date_debut), datetime.min.time()) if date_debut else None
            end_dt = datetime.combine(fields.Date.from_string(date_fin), datetime.max.time()) if date_fin else None
        except Exception:
            return {'status': 'error', 'message': 'Format de date invalide (YYYY-MM-DD attendu)'}
        Sortie = request.env['pos.livraison.sortie.stock'].sudo()
        domain = [('validated', '=', False)]
        if start_dt:
            domain.append(('date', '>=', fields.Datetime.to_string(start_dt)))
        if end_dt:
            domain.append(('date', '<=', fields.Datetime.to_string(end_dt)))
        sorties = Sortie.search(domain)
        out = [{
            'id': s.id,
            'name': s.name,
            'date': fields.Datetime.to_string(s.date) if s.date else None,
            'motif': s.motif,
            'quantite_sacs': s.quantite_sacs,
            'quantite_kg': s.quantite_kg,
            'type': s.type,
            'responsable': s.responsable,
            'notes': s.notes,
        } for s in sorties]
        return {'status': 'success', 'sorties': out, 'date_debut': date_debut, 'date_fin': date_fin}

    @http.route('/api/pos_admin/valider_stock', type='json', auth='user', methods=['POST'], csrf=False)
    def valider_stock(self, **payload):
        sortie_id = payload.get('sortie_id')
        if not sortie_id:
            return {'status': 'error', 'message': 'sortie_id requis'}
        Sortie = request.env['pos.livraison.sortie.stock'].sudo()
        s = Sortie.browse(int(sortie_id))
        if not s.exists():
            return {'status': 'error', 'message': 'Sortie introuvable'}
        if getattr(s, 'validated', False):
            return {'status': 'error', 'message': 'Déjà validée'}
        s.with_user(request.env.user).action_valider()
        return {'status': 'success', 'validated': True, 'id': s.id}
