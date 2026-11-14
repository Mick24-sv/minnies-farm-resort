"""Customer-only presentation preferences; transaction records remain intact."""
from flask import jsonify, request


def annotate_history(rows, user, kind, db):
    if user.get('role') == 'staff':
        return rows
    preferences = db(f'customer_history_visibility?user_id=eq.{int(user["id"])}&entity_kind=eq.{kind}&select=entity_id')
    hidden = {str(item['entity_id']) for item in preferences}
    return [{**row, 'hidden_from_history': str(row['id']) in hidden} for row in rows]


def install_history_routes(app, rpc, actor, handled, error):
    @app.post('/api/history/<kind>/<int:entity_id>')
    @handled
    def set_history_visibility(kind, entity_id):
        user = actor()
        if user.get('role') != 'guest':
            raise error('Only customers can organize their own history.', 403)
        data = request.get_json(silent=True)
        if kind not in ('booking', 'service') or not isinstance(data, dict) or type(data.get('hidden')) is not bool:
            raise error('Choose a room or service and a valid hide or restore action.')
        return jsonify(rpc('resort_set_history_visibility', {
            'p_actor_id': int(user['id']), 'p_kind': kind,
            'p_entity_id': entity_id, 'p_hidden': data['hidden'],
        }))
