"""Compatible entrypoint for guarded sample replacement."""

from cli.replace_samples import main
from services.sample_replacement import replace_samples


if __name__ == "__main__":
    main()
