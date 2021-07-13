import json
import os
import redis
from datetime import datetime
from werkzeug.wrappers import Request, Response
from werkzeug.routing import Map, Rule
from werkzeug.exceptions import HTTPException, NotFound
from werkzeug.middleware.shared_data import SharedDataMiddleware
from werkzeug.utils import redirect
from jinja2 import Environment, FileSystemLoader


class BulletinBoard(object):

    def __init__(self, config):
        self.redis = redis.Redis(config['redis_host'], config['redis_port'])
        template_path = os.path.join(os.path.dirname(__file__), 'templates')
        self.jinja_env = Environment(loader=FileSystemLoader(template_path),
                                     autoescape=True)
        self.url_map = Map([
            Rule('/', endpoint='all_announcements'),
            Rule('/new', endpoint='add_announcement'),
            Rule('/<announcement_id>', endpoint='single_announcement'),
            Rule('/<announcement_id>/edit', endpoint='edit_announcement'),
        ])
        self.announcements = self.get_announcements()

    def get_announcements(self):
        announcements_json = self.redis.lrange('announcements', 0, -1)
        announcements = [json.loads(announcement) for announcement in announcements_json]
        announcements.sort(
            key=lambda announcement: datetime.strptime(announcement['timestamp'], '%d/%m/%Y %H:%M:%S'),
            reverse=True
        )
        return announcements

    def on_all_announcements(self, request):
        self.announcements = self.get_announcements()
        return self.render_template('all_announcements.html',
                                    announcements=self.announcements
                                    )

    def on_add_announcement(self, request):
        if request.method == 'POST':
            self.add_announcement(request)
            return redirect('/')
        return self.render_template('add_announcement.html')

    def add_announcement(self, request):
        announcement_id = self.redis.incr('last-announcement-id')
        author = request.form['author']
        title = request.form['title']
        content = request.form['content']
        timestamp = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        announcement = {
            'id': announcement_id,
            'author': author,
            'title': title,
            'content': content,
            'timestamp': timestamp,
            'comments': [],
            'is_edited': False,
        }

        announcement_json = json.dumps(announcement)
        self.redis.rpush('announcements', announcement_json)

    def on_single_announcement(self, request, announcement_id):

        if request.method == 'POST':
            self.save_comment(request, announcement_id)
            return redirect(f'/{announcement_id}')

        for announcement in self.announcements:
            if announcement['id'] == int(announcement_id):
                single_announcement = announcement
                return self.render_template('single_announcement.html',
                                            id=single_announcement['id'],
                                            author=single_announcement['author'],
                                            title=single_announcement['title'],
                                            content=single_announcement['content'],
                                            timestamp=single_announcement['timestamp'],
                                            comments=single_announcement['comments'],
                                            edited=single_announcement['is_edited'],
                                            )
        raise NotFound()

    def save_comment(self, request, announcement_id):
        commentator = request.form['commentator-name']
        comment_text = request.form['comment']
        comment = {
            'commentator': commentator,
            'comment_text': comment_text,
        }
        for index, announcement in enumerate(self.announcements):
            if announcement['id'] == int(announcement_id):
                announcement['comments'].append(comment)
                self.redis.lset('announcements', index, json.dumps(announcement))
                break

    def on_edit_announcement(self, request, announcement_id):

        if request.method == 'POST':
            self.edit_announcement(request, announcement_id)
            return redirect(f'/{announcement_id}')

        for announcement in self.announcements:
            if announcement['id'] == int(announcement_id):
                single_announcement = announcement
                return self.render_template('edit_announcement.html',
                                            id=single_announcement['id'],
                                            author=single_announcement['author'],
                                            title=single_announcement['title'],
                                            content=single_announcement['content'],
                                            )
        raise NotFound()

    def edit_announcement(self, request, announcement_id):
        for index, announcement in enumerate(self.announcements):
            if announcement['id'] == int(announcement_id):
                announcement['title'] = request.form['title']
                announcement['author'] = request.form['author']
                announcement['content'] = request.form['content']
                announcement['timestamp'] = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
                announcement['is_edited'] = True
                self.redis.lset('announcements', index, json.dumps(announcement))
                break

    def render_template(self, template_name, **context):
        t = self.jinja_env.get_template(template_name)
        return Response(t.render(context), mimetype='text/html')

    def dispatch_request(self, request):
        adapter = self.url_map.bind_to_environ(request.environ)
        try:
            endpoint, values = adapter.match()
            return getattr(self, f'on_{endpoint}')(request, **values)
        except HTTPException as e:
            return e

    def wsgi_app(self, environ, start_response):
        request = Request(environ)
        response = self.dispatch_request(request)
        return response(environ, start_response)

    def __call__(self, environ, start_response):
        return self.wsgi_app(environ, start_response)


def create_app(redis_host='localhost', redis_port=6379, with_static=True):
    app = BulletinBoard({
        'redis_host':       redis_host,
        'redis_port':       redis_port
    })
    if with_static:
        app.wsgi_app = SharedDataMiddleware(app.wsgi_app, {
            '/static':  os.path.join(os.path.dirname(__file__), 'static')
        })
    return app
