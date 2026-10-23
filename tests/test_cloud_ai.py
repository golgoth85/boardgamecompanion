from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from boardgamecompanion.answer_generation import CloudGenerationProvider, AnswerProviderError
from boardgamecompanion.app_settings import AppSettingsStore, resolve_rag_settings
from boardgamecompanion.cloud_ai import CloudAIClient, CloudAIError, DEFAULT_MODELS, MAX_RESPONSE_BYTES
from boardgamecompanion.database import Database
from boardgamecompanion.deepseek_search import DeepSeekPriceProvider, DeepSeekRulebookProvider, public_url
from boardgamecompanion.main import app
from boardgamecompanion.rulebooks import RulebookQuery, RulebookSource
from boardgamecompanion.settings import settings


def make_client(handler, provider='deepseek'):
    return CloudAIClient(provider=provider, api_key='secret-test-key', model=DEFAULT_MODELS[provider],
                         client=httpx.Client(transport=httpx.MockTransport(handler)))


def response(text):
    return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': text}}]})


@pytest.mark.parametrize('provider', ['deepseek', 'groq'])
def test_cloud_generation_preserves_evidence_and_repair(provider):
    calls = []
    def handler(request):
        assert request.headers['Authorization'] == 'Bearer secret-test-key'
        if request.method == 'GET':
            return httpx.Response(200, json={'data': [{'id': DEFAULT_MODELS[provider], 'name': 'Model v1'}]})
        payload = json.loads(request.content)
        calls.append(payload)
        return response(json.dumps({'status': 'not_found', 'claims': []}))
    client = make_client(handler, provider)
    generator = CloudGenerationProvider(client)
    descriptor = generator.describe()
    evidence = [{'evidence_id': 'E1', 'text': 'Draw two cards.'}]
    result = generator.generate(query='Quante carte?', evidence=evidence, descriptor=descriptor,
                                max_claims=3, repair_instruction='Copy the quote verbatim.')
    assert result == {'status': 'not_found', 'claims': []}
    assert descriptor.provider == provider and len(descriptor.model_digest) == 64
    assert 'Copy the quote verbatim.' in calls[0]['messages'][0]['content']
    assert json.loads(calls[0]['messages'][1]['content'])['evidence'] == evidence
    assert calls[0]['response_format'] == {'type': 'json_object'}
    if provider == 'deepseek':
        assert calls[0]['thinking'] == {'type': 'disabled'}
    else:
        assert calls[0]['reasoning_effort'] == 'low'


@pytest.mark.parametrize('status', [301, 401, 402, 403, 429, 500])
def test_cloud_errors_do_not_echo_credentials_or_provider_body(status):
    client = make_client(lambda request: httpx.Response(status, json={'error': 'secret-test-key private question'},
                                                       headers={'location': 'https://other.test/'}))
    with pytest.raises(CloudAIError) as error:
        client.text('System', 'Private question')
    assert 'secret-test-key' not in str(error.value)
    assert 'private question' not in str(error.value)
    assert str(status) in str(error.value)


def test_cloud_response_limits_and_truncation():
    with pytest.raises(CloudAIError, match='troppo grande'):
        make_client(lambda request: httpx.Response(200, content=b' ' * (MAX_RESPONSE_BYTES + 1))).models()
    client = make_client(lambda request: httpx.Response(200, json={'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}))
    with pytest.raises(CloudAIError, match='incompleta'):
        client.structured('System', {})
    with pytest.raises(CloudAIError, match='JSON'):
        make_client(lambda request: response('not JSON')).structured('System', {})


def test_model_descriptor_rejects_missing_model_and_tracks_display_revision():
    client = make_client(lambda request: httpx.Response(200, json={'data': [{'id': 'other'}]}))
    with pytest.raises(AnswerProviderError, match='non è disponibile'):
        CloudGenerationProvider(client).describe()


@pytest.fixture
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'config_dir', tmp_path / 'config')
    monkeypatch.setattr(settings, 'import_dir', tmp_path / 'imports')
    monkeypatch.setattr(settings, 'manuals_dir', tmp_path / 'manuals')
    monkeypatch.setattr(settings, 'deepseek_api_key', None)
    monkeypatch.setattr(settings, 'groq_api_key', None)
    settings.ensure_directories()
    database = Database(settings.database_path)
    database.initialize()
    return database


def test_cloud_settings_preserve_existing_providers_and_hide_keys(isolated_database):
    with TestClient(app) as client:
        payload = {'embedding_provider_order': ['lmstudio', 'gemini', 'ollama'],
                   'generation_provider_order': ['deepseek', 'groq', 'gemini', 'lmstudio', 'ollama'],
                   'deepseek_api_key': 'deepseek-test-secret', 'groq_api_key': 'groq-test-secret',
                   'web_provider': 'deepseek'}
        saved = client.put('/api/settings/rag', json=payload)
        assert saved.status_code == 200, saved.text
        assert 'test-secret' not in saved.text
        data = saved.json()
        assert data['generation_provider_order'] == payload['generation_provider_order']
        assert data['embedding_provider_order'] == payload['embedding_provider_order']
        assert data['web_provider'] == 'deepseek'
        assert data['providers']['groq']['api_key_configured']
        rows = AppSettingsStore(isolated_database).get_many(('rag_deepseek_api_key', 'rag_groq_api_key'))
        assert rows['rag_deepseek_api_key'] == 'deepseek-test-secret'
        # Older clients may omit the new fields: a save must retain the new secrets/models.
        saved = client.put('/api/settings/rag', json={'embedding_provider_order': ['lmstudio'], 'generation_provider_order': ['groq']})
        assert saved.status_code == 200
        assert saved.json()['providers']['deepseek']['api_key_configured']
        assert saved.json()['web_provider'] == 'deepseek'
        cleared = client.put('/api/settings/rag', json={**payload, 'clear_deepseek_api_key': True})
        assert not cleared.json()['providers']['deepseek']['api_key_configured']
        for order in [['deepseek', 'deepseek'], ['unknown']]:
            assert client.put('/api/settings/rag', json={**payload, 'generation_provider_order': order}).status_code in (400, 422)
        assert client.put('/api/settings/rag', json={**payload, 'embedding_provider_order': ['deepseek']}).status_code == 422


def test_cloud_verification_is_read_only_and_redacted(isolated_database, monkeypatch):
    import boardgamecompanion.cloud_ai as module
    def models(self):
        assert self.api_key == 'pending-secret'
        return [{'id': self.model, 'name': self.model}]
    monkeypatch.setattr(module.CloudAIClient, 'models', models)
    with TestClient(app) as client:
        result = client.post('/api/settings/ai/deepseek/verify', json={'api_key': 'pending-secret'})
        assert result.status_code == 200 and result.json()['verified']
        assert 'pending-secret' not in result.text
        assert AppSettingsStore(isolated_database).get('rag_deepseek_api_key') is None


def test_web_selection_and_embedding_space_are_independent(isolated_database):
    store = AppSettingsStore(isolated_database)
    store.set('rag_embedding_provider_order', '["lmstudio"]')
    store.set('rag_generation_provider_order', '["groq","deepseek","gemini"]')
    rag = resolve_rag_settings(isolated_database)
    assert rag.web_provider == 'deepseek'
    assert rag.embedding_provider == 'lmstudio'
    store.set('rag_web_provider', 'gemini')
    assert resolve_rag_settings(isolated_database).web_provider == 'gemini'


@pytest.mark.parametrize('url', ['http://example.com/x', 'https://localhost/x', 'https://192.168.1.55/x', 'https://user:pass@example.com/x'])
def test_web_rejects_private_and_credentialed_urls(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_rulebook_search_remains_review_only_and_rejects_wrong_identity():
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={'results': [
            {'url': 'https://publisher.test/catan.pdf', 'title': 'Catan', 'content': ''},
            {'url': 'https://publisher.test/expansion.pdf', 'title': 'Catan Seafarers', 'content': ''},
            {'url': 'https://127.0.0.1/manual.pdf', 'title': 'Catan', 'content': ''},
        ]})
    provider = DeepSeekRulebookProvider(make_client(handler))
    results = provider.discover(RulebookQuery(bgg_id=13, title='Catan'))
    assert len(results) == 1
    candidate = results[0]
    assert candidate.source_kind == RulebookSource.GENERIC and candidate.confidence == 40
    assert candidate.bgg_id is None and candidate.official is False
    assert len(calls) == 2


def test_price_requires_fetched_known_url_and_verbatim_price():
    requests = []
    def handler(request):
        path = request.url.path
        requests.append(path)
        if path.endswith('/search'):
            return httpx.Response(200, json={'results': [
                {'url': 'https://dungeondice.it/catan', 'title': 'Catan'},
                {'url': 'https://untrusted.test/catan', 'title': 'Catan'},
            ]})
        if path.endswith('/fetch'):
            return httpx.Response(200, json={'title': 'Catan', 'content': 'Catan. Prezzo 29,99 EUR. Disponibile.'})
        return response(json.dumps({'offers': [
            {'url': 'https://dungeondice.it/catan', 'price_eur': 29.99, 'availability': 'in_stock', 'quote': 'Prezzo 29,99 EUR'},
            {'url': 'https://untrusted.test/catan', 'price_eur': 1, 'quote': '1,00 EUR'},
        ]}))
    offers = DeepSeekPriceProvider(make_client(handler)).search(title='Catan', year=1995)
    assert len(offers) == 1 and offers[0]['price_eur'] == 29.99
    assert requests.count('/v1/tools/fetch') == 1


def test_price_rejects_hallucinated_price_even_on_known_shop():
    def handler(request):
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [{'url': 'https://dungeondice.it/catan', 'title': 'Catan'}]})
        if request.url.path.endswith('/fetch'):
            return httpx.Response(200, json={'title': 'Catan', 'content': 'Prezzo 29,99 EUR'})
        return response(json.dumps({'offers': [{'url': 'https://dungeondice.it/catan', 'price_eur': 9.99, 'quote': 'Prezzo 29,99 EUR'}]}))
    assert DeepSeekPriceProvider(make_client(handler)).search(title='Catan') == []


@pytest.mark.parametrize('provider', ['deepseek', 'groq'])
def test_all_editorial_services_route_to_cloud_and_cache(isolated_database, tmp_path, monkeypatch, provider):
    from datetime import UTC, datetime
    import boardgamecompanion.description_translation as translation
    import boardgamecompanion.gameplay_summary as gameplay
    import boardgamecompanion.catalog_assistant as assistant
    import boardgamecompanion.suggestion_editorial as editorial
    now = datetime.now(UTC).isoformat()
    with isolated_database.transaction() as connection:
        connection.execute('INSERT INTO board_games(bgg_id,title,original_title,item_type,created_at,updated_at) VALUES(123456,\'Synthetic Game\',\'Synthetic Game\',\'standalone\',?,?)', (now, now))
        game_id = connection.execute('SELECT id FROM board_games WHERE bgg_id=123456').fetchone()[0]
        connection.execute('INSERT INTO collection_entries(board_game_id,own,created_at,updated_at) VALUES(?,1,?,?)', (game_id, now, now))
        connection.execute('INSERT INTO board_game_enrichments(board_game_id,source,external_id,description,next_refresh_at,created_at,updated_at) VALUES(?,\'bgg_xml_api2\',\'123456\',\'Players draft cards and score sets.\',\'2099-01-01\',?,?)', (game_id, now, now))
    AppSettingsStore(isolated_database).set('rag_generation_provider_order', json.dumps([provider]))
    calls = []
    class FakeCloud:
        def text(self, system, prompt, **kwargs):
            calls.append('translation')
            return 'I giocatori scelgono carte e ottengono punti con i set.'
        def structured(self, system, payload, **kwargs):
            if 'games' in payload:
                calls.append('gameplay')
                return {'summaries': [{'bgg_id': 123456, 'summary': 'Si scelgono carte e si combinano in set per ottenere punti.'}]}
            if 'catalog' in payload:
                calls.append('assistant')
                return {'answer': 'Prova Synthetic Game.', 'recommendations': [{'bgg_id': 123456, 'reason': 'È presente nella tua ludoteca.'}]}
            calls.append('editorial')
            return {'items': [{'bgg_id': 123456, 'game_summary_it': 'Si scelgono carte.', 'why_it_fits': 'Un gioco di carte per la tua ludoteca.'}]}
    for module in (translation, gameplay, assistant, editorial):
        monkeypatch.setattr(module, 'cloud_client', lambda *args, **kwargs: FakeCloud())
    service = translation.DescriptionTranslationService(isolated_database)
    first = service.translate(123456)
    service.translate(123456)
    assert first['translation']['provider'] == provider
    service2 = gameplay.GameplaySummaryService(isolated_database)
    first2 = service2.ensure_many([123456])
    service2.ensure_many([123456])
    assert first2['items'][0]['provider'] == provider
    result = assistant.CatalogAssistantService(isolated_database).ask('Cosa giochiamo?')
    assert result['provider'] == provider
    service3 = editorial.SuggestionEditorialService(isolated_database, cache_path=tmp_path / 'editorial.json')
    item = {'bgg_id': 123456, 'title': 'Synthetic Game', 'source_description': 'A card game.'}
    result3 = service3.enrich([item])
    service3.enrich([item])
    assert result3[0]['editorial_provider'] == provider
    assert calls.count('translation') == calls.count('gameplay') == calls.count('editorial') == 1


def test_editorial_does_not_fall_back_to_excluded_gemini(isolated_database, tmp_path, monkeypatch):
    import boardgamecompanion.suggestion_editorial as editorial
    store = AppSettingsStore(isolated_database)
    store.set('rag_generation_provider_order', '["deepseek"]')
    store.set('rag_gemini_api_key', 'configured-but-excluded', sensitive=True)
    def unavailable(*args, **kwargs):
        raise CloudAIError('DeepSeek non disponibile')
    monkeypatch.setattr(editorial, 'cloud_client', unavailable)
    service = editorial.SuggestionEditorialService(isolated_database, cache_path=tmp_path / 'editorial.json')
    monkeypatch.setattr(service, '_gemini', lambda *args: pytest.fail('Provider escluso chiamato'))
    with pytest.raises(editorial.SuggestionEditorialError, match='No editorial'):
        service._generate([{'bgg_id': 1, 'title': 'Game'}])


def test_price_fetch_outage_is_an_error_so_cached_prices_are_preserved():
    def handler(request):
        if request.url.path.endswith('/search'):
            return httpx.Response(200, json={'results': [{'url': 'https://dungeondice.it/catan', 'title': 'Catan'}]})
        return httpx.Response(503)
    from boardgamecompanion.price_search import PriceSearchError
    with pytest.raises(PriceSearchError, match='prezzi precedenti conservati'):
        DeepSeekPriceProvider(make_client(handler)).search(title='Catan')


def test_groq_qwen_hides_reasoning_and_model_can_be_overridden():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return response('Testo.')
    client = CloudAIClient(provider='groq', api_key='secret-test-key', model='qwen/qwen3.8-27b',
                           client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert client.text('sistema', 'utente') == 'Testo.'
    assert seen[0]['reasoning_format'] == 'hidden' and 'reasoning_effort' not in seen[0]

    from boardgamecompanion.cloud_ai import cloud_client
    rag = type('Rag', (), {'generation_provider': 'groq', 'groq_api_key': 'k',
                           'groq_generation_model': 'openai/gpt-oss-120b'})()
    assert cloud_client(rag, 'groq').model == 'openai/gpt-oss-120b'
    assert cloud_client(rag, 'groq', model='qwen/qwen3.8-27b').model == 'qwen/qwen3.8-27b'
