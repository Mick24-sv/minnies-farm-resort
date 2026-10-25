"""Private, persistent transaction notifications. Recipients come from the login token."""
from flask import jsonify, request


def install_notification_routes(app, rpc, actor, handled):
    @app.get('/api/notifications')
    @handled
    def list_notifications():
        user = actor()
        before = request.args.get('before')
        before_id = int(before) if before else None
        # Expiration also works while a signed-in guest is waiting on another page.
        rpc('resort_expire_holds')
        rpc('resort_expire_service_holds')
        return jsonify(rpc('resort_list_notifications', {
            'p_actor_id': int(user['id']), 'p_before': before_id,
        }))

    @app.post('/api/notifications/read')
    @handled
    def read_notifications():
        user = actor()
        notification_id = (request.get_json() or {}).get('id')
        return jsonify(rpc('resort_read_notifications', {
            'p_actor_id': int(user['id']),
            'p_notification_id': int(notification_id) if notification_id is not None else None,
        }))
