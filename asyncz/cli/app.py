from __future__ import annotations

from sayer import Sayer

from asyncz.cli.commands.add import add
from asyncz.cli.commands.list import list_jobs
from asyncz.cli.commands.pause import pause
from asyncz.cli.commands.remove import remove
from asyncz.cli.commands.resume import resume
from asyncz.cli.commands.run import run
from asyncz.cli.commands.start import start

asyncz_cli = Sayer(name="asyncz", help="Asyncz scheduler CLI")


asyncz_cli.add_command(add)
asyncz_cli.add_command(remove)
asyncz_cli.add_command(run)
asyncz_cli.add_command(pause)
asyncz_cli.add_command(resume)
asyncz_cli.add_command(start)
asyncz_cli.add_command(list_jobs)


def main() -> None:
    asyncz_cli()
