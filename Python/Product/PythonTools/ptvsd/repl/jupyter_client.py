﻿# Python Tools for Visual Studio
# Copyright(c) Microsoft Corporation
# All rights reserved.
# 
# Licensed under the Apache License, Version 2.0 (the License); you may not use
# this file except in compliance with the License. You may obtain a copy of the
# License at http://www.apache.org/licenses/LICENSE-2.0
# 
# THIS CODE IS PROVIDED ON AN  *AS IS* BASIS, WITHOUT WARRANTIES OR CONDITIONS
# OF ANY KIND, EITHER EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION ANY
# IMPLIED WARRANTIES OR CONDITIONS OF TITLE, FITNESS FOR A PARTICULAR PURPOSE,
# MERCHANTABLITY OR NON-INFRINGEMENT.
# 
# See the Apache Version 2.0 License for specific language governing
# permissions and limitations under the License.

from __future__ import absolute_import, print_function

"""Implements REPL support over IPython/ZMQ for VisualStudio"""

__author__ = "Microsoft Corporation <ptvshelp@microsoft.com>"
__version__ = "3.2.1.0"

import ast
import base64
import errno
import re
import sys
import threading
import time
import traceback
from ptvsd.repl import BasicReplBackend, ReplBackend, UnsupportedReplException, _command_line_to_args_list
from ptvsd.util import to_bytes

try:
    import jupyter_client
    import jupyter_client.manager
except ImportError:
    raise UnsupportedReplException("Jupyter mode requires the jupyter_client and ipykernel packages. " + traceback.format_exc())

try:
    import _thread
except ImportError:
    import thread as _thread    # legacy name

try:
    from queue import Empty
except ImportError:
    from Queue import Empty

# Use safer eval
eval = ast.literal_eval

class Message(object):
    _sentinel = object()

    def __init__(self, msg):
        self._m = msg
        self._read = False

    def __getattr__(self, attr):
        return self[attr]

    def __getitem__(self, key):
        if isinstance(key, tuple):
            key, default_value = key
        else:
            default_value = self._sentinel
        if not self._m:
            return self
        try:
            v = self._m[key]
        except KeyError:
            if default_value is self._sentinel:
                return Message({})
            return default_value
        if not isinstance(v, dict):
            return v
        return Message(v)

    def __repr__(self):
        return repr(self._m)

class JupyterClientBackend(ReplBackend):
    def __init__(self, mod_name='__main__', launch_file=None):
        super(JupyterClientBackend, self).__init__()
        self.__client = None

        # This lock will be released when we should shut down
        self.__exit = threading.Lock()
        self.__exit.acquire()

        self.__lock = threading.RLock()
        self.__status = 'idle'
        self.__msg_buffer = []
        self.__execution_count = 0
        self.__cmd_buffer = []
        self.__on_reply = {}

    def execution_loop(self):
        """starts processing execution requests"""
        try:
            return self._execution_loop()
        except:
            traceback.print_exc()
            input()
            raise

    def _execution_loop(self):
        km, kc = jupyter_client.manager.start_new_kernel()
        try:
            self.exit_requested = False
            self.__client = kc
            self.send_cwd()

            self.__shell_thread = _thread.start_new_thread(self.__shell_threadproc, (kc,))
            self.__iopub_thread = _thread.start_new_thread(self.__iopub_threadproc, (kc,))

            self.__exit.acquire()

            self.send_exit()
        finally:
            kc.stop_channels()
            km.shutdown_kernel(now=True)

    def __command_executed(self, msg):
        self.send_command_executed()

    def run_command(self, command):
        """runs the specified command which is a string containing code"""
        if self.__client:
            with self.__lock:
                self.__exec(command, store_history=True, silent=False).append(self.__command_executed)
            return True

        self.__cmd_buffer.append(command)
        return False

    def __exec(self, command, store_history=False, allow_stdin=False, silent=True, get_vars=None):
        with self.__lock:
            msg_id = self.__client.execute(
                command,
                store_history=store_history,
                allow_stdin=allow_stdin,
                silent=silent,
                user_expressions=get_vars,
            )
            return self.__on_reply.setdefault((msg_id, 'execute_reply'), [])

    def execute_file_ex(self, filetype, filename, args):
        """executes the given filename as a 'script', 'module' or 'process'."""
        if filetype == 'script':
            pass
        elif filetype == 'module':
            pass
        elif filetype == 'process':
            pass

    def interrupt_main(self):
        """aborts the current running command"""
        #raise NotImplementedError
        pass

    def exit_process(self):
        """exits the REPL process"""
        self.exit_requested = True
        self.__exit.release()

    def get_members(self, expression):
        """returns a tuple of the type name, instance members, and type members"""
        raise NotImplementedError

    def get_signatures(self, expression):
        """returns doc, args, vargs, varkw, defaults."""
        raise NotImplementedError

    def set_current_module(self, module):
        """sets the module which code executes against"""
        raise NotImplementedError

    def set_current_thread_and_frame(self, thread_id, frame_id, frame_kind):
        """sets the current thread and frame which code will execute against"""
        raise NotImplementedError

    def get_module_names(self):
        """returns a list of module names"""
        raise NotImplementedError

    def flush(self):
        """flushes the stdout/stderr buffers"""
        pass

    def __shell_threadproc(self, client):
        try:
            last_exec_count = None
            on_replies = self.__on_reply
            while not self.exit_requested:
                while self.__cmd_buffer and not self.exit_requested:
                    self.run_command(self.__cmd_buffer.pop(0))

                m = Message(client.get_shell_msg(block=True))
                msg_id = m.msg_id
                msg_type = m.msg_type

                print('%s: %s' % (msg_type, msg_id))
                #print(m)

                exec_count = m.content['execution_count', None]
                if exec_count != last_exec_count:
                    last_exec_count = exec_count
                    exec_count = int(exec_count) + 1
                    ps1 = 'In  [%s]: ' % exec_count
                    ps2 = ' ' * (len(ps1) - 5) + '...: '
                    self.send_prompt(ps1, ps2, allow_multiple_statements=True)

                parent_id = m.parent_header['msg_id', None]
                if parent_id:
                    on_reply = on_replies.pop((parent_id, msg_type), ())
                    for callable in on_reply:
                        callable(m)

        except KeyboardInterrupt:
            self.exit_process()
        except:
            traceback.print_exc()
            input()
            self.exit_process()

    def __iopub_threadproc(self, client):
        try:
            last_exec_count = None
            while not self.exit_requested:
                m = Message(client.get_iopub_msg(block=True))

                if m.msg_type == 'execute_input':
                    pass
                elif m.msg_type == 'execute_result':
                    print(m.msg_type, m.content)
                    self.__write_result(m.content)
                elif m.msg_type == 'display_data':
                    print(m.msg_type, m.content)
                    self.__write_content(m.content)
                elif m.msg_type == 'stream':
                    self.__write_stream(m.content)
                elif m.msg_type == 'error':
                    self.__write_error(m.content)
                elif m.msg_type == 'status':
                    self.__status = m.content['execution_state', 'idle']
                else:
                    print("Received: " + str(m) + "\n")
                    self.write_stdout(str(m) + '\n')

        except KeyboardInterrupt:
            self.exit_process()
        except:
            traceback.print_exc()
            input()
            self.exit_process()

    def __write_stream(self, content):
        if content.name == 'stderr':
            f = self.write_stderr
        else:
            f = self.write_stdout
        text = content.text
        if text:
            f(text)

    def __write_result(self, content):
        exec_count = content['execution_count', None]
        if exec_count is not None:
            prefix = 'Out [%s]: ' % exec_count
        else:
            prefix = 'Out: '

        if content.status == 'ok':
            output_str = content.data['text/plain', None]
            if output_str is None:
                output_str = str(content.data)
            if '\n' in output_str:
                output_str = '%s\n%s\n' % (prefix, output_str)
            else:
                output_str = prefix + output_str + '\n'
            self.write_stdout(output_str)
            return

        if content.status == 'error':
            tb = content['traceback', None]
            if tb:
                self.write_stderr(prefix + '\n')
                for line in tb:
                    self.write_stderr(line + '\n')
                return

        self.write_stderr(str(content) + '\n')
        self.send_error()

    def __write_content(self, content):
        if content.status != 'ok':
            return

        output_xaml = content.data['application/xaml+xml', None]
        if output_xaml is not None:
            try:
                if isinstance(output_xaml, str) and sys.version_info[0] >= 3:
                    output_xaml = output_xaml.encode('ascii')
                self.write_stdout(prefix)
                self.write_xaml(base64.decodestring(output_xaml))
                self.write_stdout('\n\n')
                return
            except:
                pass

        output_png = content.data['image/png', None]
        if output_png is not None:
            try:
                if isinstance(output_png, str) and sys.version_info[0] >= 3:
                    output_png = output_png.encode('ascii')
                self.write_stdout(prefix)
                self.write_png(base64.decodestring(output_png))
                self.write_stdout('\n\n')
                return
            except:
                pass

if __name__ == '__main__':
    b = JupyterClientBackend()
    b.execution_loop()

