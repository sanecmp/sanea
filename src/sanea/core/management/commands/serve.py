"""Run the embedded HTTP and HTTPS Cheroot servers."""

import logging
import signal
from types import FrameType

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.core.wsgi import get_wsgi_application

from ....exceptions import ServerError
from ....network.server import ServerRunner, create_servers
from ...services.registration_window import is_registration_discovery_available, registration_window


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Run the browser UI and sanex API listeners."""

    help = "Run sanea using the embedded HTTP and HTTPS server"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--open-registration",
            action="store_true",
            help="open one registration window when the listeners start",
        )

    def handle(self, *args: object, **options: object) -> None:
        server_host = settings.SERVER_HOST
        http_port = settings.HTTP_PORT
        https_port = settings.HTTPS_PORT
        discovery_port = settings.DISCOVERY_PORT
        pki_dir = settings.PKI_DIR
        sigterm = signal.SIGTERM
        set_signal = signal.signal
        write = self.stdout.write
        try:
            servers = create_servers(
                get_wsgi_application(),
                server_host,
                http_port,
                https_port,
                discovery_port,
                pki_dir,
                is_registration_discovery_available,
            )
            runner = ServerRunner(servers)
            request_stop = runner.request_stop
            previous_handler = signal.getsignal(sigterm)

            def stop_on_signal(signum: int, frame: FrameType | None) -> None:
                request_stop()

            set_signal(sigterm, stop_on_signal)
            logger.info("HTTP listening on %s:%d", server_host, http_port)
            logger.info("HTTPS listening on %s:%d", server_host, https_port)
            logger.info("UDP discovery on %s:%d", server_host, discovery_port)
            logger.info("CA certificate: %s", pki_dir / "ca.crt")

            if options["open_registration"]:
                snapshot = registration_window.open()
                write(f"SANEA_REGISTRATION_CODE={snapshot.code}")

            try:
                runner.run()

            except KeyboardInterrupt:
                request_stop()
            finally:
                set_signal(sigterm, previous_handler)

        except ServerError as error:
            raise CommandError(f"{error}") from error
