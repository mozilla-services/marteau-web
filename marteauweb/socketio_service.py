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
            for line in console.split('\n'):
                if line == '':
                    continue
                self.emit("console.%s" % jobid, line + '\n')

            pos = len(console)
        else:
            pos = 0


        status = status and status.get('msg', 'Running') or 'Running'

        while status == 'Running':
            status, console = queue.get_result(jobid)
            status = status and status.get('msg', 'Running') or 'Running'

            if console is not None:
                console = console.split('\n')

                for line in console[pos:]:
                    if line == '':
                        continue
                    self.emit("console.%s" % jobid, line + '\n')

                pos = len(console)
            gevent.sleep(.5)

    def on_subscribe(self, console, *args, **kwargs):
        jobid = console.split('.')[-1]
        self.spawn(partial(self.listener, jobid))


@view_config(route_name='socket_io')
def socketio_service(request):
    retval = socketio_manage(request.environ,
        {
            '': ConsoleNamespace,
        }, request=request
    )

    return retval
