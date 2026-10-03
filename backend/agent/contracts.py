"""Data-only commands passed between tools, review cards, and approval."""
from dataclasses import asdict, dataclass
import json
from services.validation import ValidationError

@dataclass(frozen=True)
class AgentCommand:
    kind: str
    identity: dict[str, str]
    data: dict


def command_dicts(commands: object) -> list[dict]:
    if not isinstance(commands, list) or not 1 <= len(commands) <= 64:
        raise ValidationError('commands', '変更案には1〜64件の操作を指定してください。')
    result = []
    for value in commands:
        item = asdict(value) if isinstance(value, AgentCommand) else value
        if not isinstance(item, dict) or set(item) != {'kind', 'identity', 'data'}:
            raise ValidationError('commands', '操作の形式が正しくありません。')
        if item['kind'] not in ('transaction.create', 'transaction.update', 'trajectory.create', 'trajectory.update'):
            raise ValidationError('commands', '許可されていない操作です。')
        if not isinstance(item['identity'], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in item['identity'].items()) or not isinstance(item['data'], dict):
            raise ValidationError('commands', '操作の対象と内容を確認してください。')
        result.append(item)
    try:
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValidationError('commands', '操作には有効なJSONを使用してください。') from error
    if len(encoded.encode()) > 512 * 1024:
        raise ValidationError('commands', '変更案が大きすぎます。')
    return json.loads(encoded)
