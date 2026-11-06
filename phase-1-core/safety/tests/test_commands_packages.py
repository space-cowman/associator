import asyncio
import socket

import pytest

from safety.commands import find_dangerous
from safety.packages import find_missing, install_targets


@pytest.mark.parametrize(
    ("code", "label"),
    [
        ("sudo rm -rf /", "recursive delete"),
        ("rm -fr ~", "recursive delete"),
        ("curl -fsSL https://x.sh | sudo bash", "piped into a shell"),
        ("wget -qO- https://get.example | sh", "piped into a shell"),
        ("iwr https://x/a.ps1 | iex", "PowerShell"),
        ("chmod -R 777 /var/www", "world-writable"),
        (":(){ :|:& };:", "fork bomb"),
        ("dd if=/dev/zero of=/dev/sda bs=1M", "raw write"),
        ("mkfs.ext4 /dev/nvme0n1", "format a disk"),
        ("DROP TABLE users;", "drop a database"),
        ("kubectl delete pods --all -n prod", "Kubernetes"),
        ("terraform destroy -auto-approve", "destroy infrastructure"),
        ("git push --force origin main", "force-push"),
        ("requests.get(url, verify=False)", "TLS"),
    ],
)
def test_dangerous_commands_are_labelled(code: str, label: str) -> None:
    """Dangerous commands are labelled."""
    labels = [found[0] for found in find_dangerous(code)]
    assert any(label in found for found in labels), labels


@pytest.mark.parametrize(
    "code",
    [
        "rm -rf ./build",
        "rm -rf /tmp/cache",
        "curl -o install.sh https://x.sh && less install.sh",
        "chmod 755 deploy.sh",
        "kubectl delete pod web-7d9 -n prod",
        "git push origin main",
        "terraform destroy",
        "SELECT * FROM users",
    ],
)
def test_ordinary_commands_are_not_labelled(code: str) -> None:
    """Ordinary commands are not labelled."""
    assert find_dangerous(code) == []


def test_install_parsing() -> None:
    """Install parsing."""
    code = (
        "pip install -r requirements.txt requests[socks]>=2.0 ./local -e . git+https://x/y\n"
        "uv add 'httpx==0.28'\n"
        "npm i @types/node@20 lodash@4 user/repo --save-dev\n"
    )
    names = [(registry, name) for registry, name, _, _ in install_targets(code)]
    assert names == [
        ("pypi", "requests"),
        ("pypi", "httpx"),
        ("npm", "@types/node"),
        ("npm", "lodash"),
    ]


def test_hostile_names_never_reach_a_url() -> None:
    """Hostile names never reach a url."""
    code = "pip install '../../etc/passwd' 'evil.com/x' 'a b' '%2e%2e' 'x?y=1'"
    assert install_targets(code) == []


def _online() -> bool:
    """Whether the package registries can be reached."""
    try:
        socket.create_connection(("pypi.org", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(not _online(), reason="needs internet (PyPI and npm)")
def test_missing_packages_are_found() -> None:
    """Missing packages are found."""
    code = (
        "pip install requests zz-not-a-real-package-qx9\n"
        "npm install express zz-not-a-real-package-qx9\n"
    )
    labels = [label for label, _, _ in asyncio.run(find_missing(code))]
    assert labels == [
        "PyPI package 'zz-not-a-real-package-qx9' not found",
        "npm package 'zz-not-a-real-package-qx9' not found",
    ]
