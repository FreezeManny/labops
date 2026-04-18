test_conf := "./test-samples/homelab-test.yml"
runner := "uv run main.py"
system := "redhat"

pre-commit:
	uv run pre-commit run --all-files

test-validate:
	{{runner}} validate {{test_conf}}

test-host-update:
	{{runner}} host update test-system-{{system}} --config {{test_conf}}

test-host-update-all:
	{{runner}} host update --all --config {{test_conf}}

test-host-list:
	{{runner}} host list --config {{test_conf}}

test-host-setup:
	{{runner}} host setup test-system-{{system}} --config {{test_conf}}

test-vm-list:
	{{runner}} vm list --config {{test_conf}}