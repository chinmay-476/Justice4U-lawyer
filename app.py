from core import app, init_database
import routes.public_routes  # noqa: F401
import routes.auth_routes  # noqa: F401
import routes.admin_routes  # noqa: F401

if __name__ == '__main__':
    with app.app_context():
        init_database()
    app.run(debug=True, port=5001, use_reloader=False)
