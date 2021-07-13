from werkzeug.serving import run_simple
import webbrowser

from bulletin_board.bulletin_board import create_app


if __name__ == '__main__':
    app = create_app()
    webbrowser.open('http://localhost:5000/')
    run_simple('localhost', 5000, app, use_debugger=True, use_reloader=True)
