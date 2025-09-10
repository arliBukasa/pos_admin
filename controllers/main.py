from datetime import datetime as dt
from datetime import timedelta as td
from odoo import http, fields
from odoo.http import request

import logging

logging.info("=================== datetime: %s", dt.now())

class PosAdminApi(http.Controller):
    @http.route('/api/pos_admin/rapports', type='json', auth='user', methods=['POST'], csrf=False)
    def get_rapports(self, **payload):
        logging.info("================= Récupération des rapports: %s", payload)
        params = http.request.jsonrequest or payload
        payload = params
        date_debut = payload.get('date_debut')
        date_fin = payload.get('date_fin')
        session_ids = payload.get('session_ids') or payload.get('sessions') or []
        # Client sends 'caisse_sessions' (Android DTO); accept legacy 'sessions_caisse' too
        sessions_caisse = payload.get('caisse_sessions') or payload.get('sessions_caisse') or []
        # si la date debut et date fin ne sont pas fournies, on prend la date du jour pour date de fin et date hier pour date de debut
        if not date_fin:
            date_fin = fields.Date.context_today(request.env.user)
        if not date_debut:
            date_debut = fields.Date.context_today(request.env.user) - td(days=1)
        
        logging.info("================= Récupération des rapports: %s | %s| %s", payload, sessions_caisse, session_ids)
        if isinstance(session_ids, int):
            session_ids = [session_ids]
        if not isinstance(session_ids, (list, tuple)):
            session_ids = []
        try:
            start_dt = dt.combine(fields.Date.from_string(date_debut), dt.min.time()) if date_debut else None
            end_dt = dt.combine(fields.Date.from_string(date_fin), dt.max.time()) if date_fin else None
            logging.info("================= start_dt: %s, end_dt: %s, sessions: %s", start_dt, end_dt, session_ids)
        except Exception as e:
            return {'status': 'error', 'message': 'Format de date invalide (YYYY-MM-DD attendu): exception : %s' % e}

        Cmd = request.env['pos.caisse.commande'].sudo()
        Mvt = request.env['pos.caisse.mouvement'].sudo()
        Liv = request.env['pos.livraison.livraison'].sudo()
        Sortie = request.env['pos.livraison.sortie.stock'].sudo()
        Sess = request.env['pos.livraison.session'].sudo()
        Sess_caisse = request.env['pos.caisse.session'].sudo()
        # Build date domains
        def date_domain(field):
            dom = []
            if start_dt:
                dom.append((field, '>=', fields.Datetime.to_string(start_dt - td(days=1))))
            if end_dt:
                dom.append((field, '<=', fields.Datetime.to_string(end_dt)))
            return dom

        logging.info("================= date_domain: %s", date_domain('date'))
        # If livraison sessions provided, restrict livraisons/sorties to those sessions
        session_dom = []
        if session_ids:
            session_dom = [('session_id', 'in', [int(x) for x in session_ids])]  # for Livraison and Sortie
        # Caisse sessions: independent filter for commandes and mouvements
        caisse_ids = []
        if isinstance(sessions_caisse, int):
            caisse_ids = [int(sessions_caisse)]
        elif isinstance(sessions_caisse, (list, tuple)):
            caisse_ids = [int(x) for x in sessions_caisse]

        logging.info("================= caisse_ids à partir de la requette: %s", caisse_ids)

        # Commandes domain
        #commande_domain = date_domain('date')
        commande_domain = []
        if caisse_ids:
            commande_domain.append(('session_id', 'in', caisse_ids))
        else:
            # get caisse sessions in date_domain range
            caisse_sessions = Sess_caisse.search(date_domain('date'))
            if caisse_sessions:
                commande_domain.append(('session_id', 'in', caisse_sessions.ids))
                caisse_ids = caisse_sessions.ids

        commandes = Cmd.search(commande_domain)
        logging.info("================= commandes: %s | %s", commandes, commande_domain)
        ca_total = sum(commandes.mapped('total')) if commandes else 0.0
        ca_bp = sum(commandes.filtered(lambda c: c.type_paiement == 'bp').mapped('total')) if commandes else 0.0
        ca_cash = ca_total - ca_bp
        nb_commandes = len(commandes)
        # Mouvements
        mvt_extra = [('session_id', 'in', caisse_ids)] if caisse_ids else []
        mvt_entree = Mvt.search([('type', '=', 'entree')] + mvt_extra)
        mvt_sortie = Mvt.search([('type', '=', 'sortie')] + mvt_extra)
        entrees = sum(mvt_entree.mapped('montant')) if mvt_entree else 0.0
        depenses = sum(mvt_sortie.mapped('montant')) if mvt_sortie else 0.0
        resultat = entrees - depenses
        # Livraisons
        livraisons = Liv.search(date_domain('date') + session_dom)
        nb_livraisons = len(livraisons)
        montant_livre_total = sum(livraisons.mapped('montant_livre')) if livraisons else 0.0
        sacs_liv = (sum(livraisons.mapped('montant_livre'))/222000) if livraisons else 0.0
        logging.info("================= sacs livrés: %s", sacs_liv)
        # Sorties de stock (toutes)
        sorties = Sortie.search(date_domain('date') + session_dom)
        sacs_sortie = sum(sorties.mapped('quantite_sacs')) if sorties else 0.0
        montant_sorties = sum(sorties.mapped('montant')) if sorties else 0.0
        poids_sac = float(request.env['ir.config_parameter'].sudo().get_param('pos_livraison.poids_sac', 50))
        sacs_sortis = sacs_liv
        kg_sortis = sacs_sortis * poids_sac
        # Sessions in current noon window for chips
        from datetime import datetime as py_dt, timedelta
        user_tz = request.env.user.tz or request.env.context.get('tz')
        def localize_naive(dt):
            try:
                import pytz
                tz = pytz.timezone(user_tz) if user_tz else pytz.utc
                return tz.localize(dt).astimezone(pytz.utc)
            except Exception:
                return dt
        now_local = fields.Datetime.context_timestamp(request.env.user, fields.Datetime.now())
        today_local = now_local.date()
        noon_local = py_dt.combine(today_local, py_dt.min.time()).replace(hour=12)
        # Make noon timezone-aware to match now_local
        try:
            import pytz
            from datetime import datetime, timedelta
            tz = pytz.timezone(user_tz) if user_tz else pytz.utc
            noon_local = tz.localize(noon_local)
        except Exception:
            # Fallback: keep as is if localization fails
            pass
        if now_local < noon_local:
            start_local = noon_local - timedelta(days=1)
            end_local = noon_local
            logging.info("================= now_local < noon_local")
        else:
            start_local = noon_local
            end_local = noon_local + timedelta(days=1)
            logging.info("================= now_local > noon_local")
        start_utc = fields.Datetime.to_string(localize_naive(start_local))
        end_utc = fields.Datetime.to_string(localize_naive(end_local))
        logging.info("================= start_utc: %s", start_utc)
        logging.info("================= end_utc: %s", end_utc)
        sessions_window = Sess.search(date_domain('date'), order='date desc')
        logging.info("================= sessions_window: %s", sessions_window)
        sessions_payload = [{
            'id': s.id,
            'name': s.name,
            'user_id': s.user_id.id,
            'user_name': s.user_id.name,
            'state': s.state,
            'date': fields.Datetime.to_string(s.date) if s.date else None,
            'date_cloture': fields.Datetime.to_string(s.date_cloture) if s.date_cloture else None,
            'stats': {
                'total_livraisons': s.total_livraisons,
                'montant_livre_total': s.montant_livre_total,
                'sacs_livres_total': s.sacs_livres_total,
                'sorties_sacs_total': s.sorties_sacs_total,
                'sorties_kg_total': s.sorties_kg_total,
            }
        } for s in sessions_window]

        # Caisse sessions in the same noon window (for chips)
        caisse_sessions_window = Sess_caisse.search(date_domain('date'), order='date desc')
        logging.info("================= caisse_sessions_window: %s , %s", caisse_sessions_window,caisse_ids)
        caisse_sessions_payload = [{
            'id': s.id,
            'name': s.name,
            'user_id': s.user_id.id if s.user_id else None,
            'user_name': s.user_id.name if s.user_id else None,
            'state': s.state,
            'date': fields.Datetime.to_string(s.date) if s.date else None,
            'date_cloture': fields.Datetime.to_string(s.date_cloture) if s.date_cloture else None,
            'stats': {
                'total_commandes': s.total_commandes,
                'total_montant': s.total_montant,
                'total_mouvements': s.total_mouvements,
                'montant_en_caisse': s.montant_en_caisse,
                'montant_sortie': s.montant_sortie,
                'total_bp': s.total_bp,
            }
        } for s in caisse_sessions_window]
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
            'sessions': sessions_payload,
            'caisse_sessions': caisse_sessions_payload,
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
