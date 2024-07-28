import logging

from pcbasic import config, SessionAsync
from pcbasic.compat import nullcontext
from pcbasic.guard import ExceptionGuard
from pcbasic.interface import InterfaceAsync, InitFailed

async def main():
    with config.TemporaryDirectory(prefix='pcbasic-') as temp_dir:
        settings = config.Settings(temp_dir, [])

        try:
            interface = InterfaceAsync(**settings.iface_params)
        except InitFailed as e:  # pragma: no cover
            logging.error(e)
        else:
            exception_guard = ExceptionGuard(interface, **settings.guard_params)
            logging.info("exception_guard")
            await interface.launch(
                _run_session,
                interface=interface,
                exception_handler=exception_guard,
                **settings.launch_params
            )


async def _run_session(
        interface=None, exception_handler=nullcontext,
        resume=False, state_file=None,
        prog=None, commands=(), keys=u'', greeting=True, **session_params
):
    """Start or resume session, handle exceptions, suspend on exit."""
    logging.info("_run_session")
    if resume:
        try:
            session = SessionAsync.resume(state_file)
            session.add_pipes(**session_params)
        except Exception as e:
            # if we were told to resume but can't, give up
            logging.critical('Failed to resume session from %s: %s' % (state_file, e))
            return

    logging.info("Session")
    session = SessionAsync(**session_params)
    await session.start_async()
    with exception_handler(session) as handler:
        with session:
            try:
                await _operate_session(session, interface, prog, commands, keys, greeting)
            finally:
                try:
                    session.suspend(state_file)
                except Exception as e:
                    logging.error('Failed to save session to %s: %s', state_file, e)
    if exception_handler is not nullcontext and handler.exception_handled:
        await _run_session(
            interface, exception_handler, resume=True, state_file=state_file, greeting=False
        )


async def _operate_session(session, interface, prog, commands, keys, greeting):
    """Run an interactive BASIC session."""
    await session.attach(interface)
    if greeting:
        logging.info("greeting session")
        await session.greet()
    if prog:
        with session.bind_file(prog) as progfile:
            await session.execute(b'LOAD "%s"' % (progfile,))
    await session.press_keys(keys)
    for cmd in commands:
        await session.execute(cmd)
    await session.interact()
