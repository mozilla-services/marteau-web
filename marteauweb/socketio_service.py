import json
import gevent
from functools import partial

from socketio.namespace import BaseNamespace
from socketio import socketio_manage

from pyramid.view import view_config


class ConsoleNamespace(BaseNamespace):
    def listener(self, jobid):
        queue = self.request.registry['queue']
        status, console = queue.get_result(jobid)

        # XXX we should use a blocking redis queue
        # this code suck
        #
        # dumping the existing content
        if console is not None:
            pos = len(console)

            for line in console.split('\n'):
                if line == '':
                    continue
                self.emit("console.%s" % jobid, line + '\n')
        else:
            pos = 0


        status = status and status.get('msg', 'Running') or 'Running'

        while status == 'Running':
            status, console = queue.get_result(jobid)
            status = status and status.get('msg', 'Running') or 'Running'

            if console is not None:
                start = pos
                pos = len(console)

                console = console[start:].split('\n')

                for line in console:
                    if line == '':
                        continue
                    self.emit("console.%s" % jobid, line + '\n')

            gevent.sleep(.5)

    def on_subscribe(self, console, *args, **kwargs):
        jobid = console.split('.')[-1]
        self.spawn(partial(self.listener, jobid))


@view_config(route_name='socket_io', renderer='string')
def socketio_service(request):
    retval = socketio_manage(request.environ,
        {
            '': ConsoleNamespace,
        }, request=request
    )

    if retval is None:
        return ''
    return retval
