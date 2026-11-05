import json
import re

from .common import InfoExtractor
from ..utils import (
    int_or_none,
    traverse_obj,
    unified_strdate,
    url_or_none,
)


class BRIE(InfoExtractor):
    IE_DESC = 'Bayerischer Rundfunk'
    _VALID_URL = r'(?P<base_url>https?://(?:www\.)?br(?:-klassik)?\.de)/(?:[a-z0-9\-_]+/)+(?P<id>[a-z0-9\-_]+)\.html'

    _TESTS = [
        {
            'url': 'http://www.br.de/radio/bayern1/service/team/videos/team-video-erdelt100.html',
            'info_dict': {
                'id': '6ba73750-d405-45d3-861d-1ce8c524e059',
                'ext': 'mp4',
                'title': 'Uwe Erdelt: Umweltbewusster Häuslebauer',
                'description': str,
                'thumbnail': str,
                'duration': 116,
            },
        },
    ]

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        display_id = mobj.group('id')

        page = self._download_webpage(url, display_id)

        # New ARD player: ardplayer.Player('id', '~playerConfig.json', '~mediaInfo.json')
        media_info_path = self._search_regex(
            r'new\s+ardplayer\.Player\s*\([^,]+,\s*[^,]+,\s*"([^"]+~mediaInfo\.json[^"]*)"',
            page, 'media info path', default=None)

        if not media_info_path:
            # Fallback: derive path from URL
            page_path = re.sub(r'\.html$', '', re.sub(r'^https?://[^/]+', '', url))
            media_info_path = page_path + '~mediaInfo.json?isEmbed=false'

        base_url = mobj.group('base_url')
        media_info_url = base_url + media_info_path
        media_info = self._download_json(media_info_url, display_id)

        video_id = media_info.get('id') or display_id

        # Title from JSON-LD schema.org VideoObject
        json_ld = self._search_json_ld(page, display_id, default={})
        title = (
            json_ld.get('title')
            or traverse_obj(media_info, ('meta', 'title'))
            or traverse_obj(media_info, ('meta', 'seriesTitle'))
            or self._og_search_title(page, default=None)
            or display_id
        )

        description = (
            traverse_obj(media_info, ('meta', 'synopsis'))
            or media_info.get('comment')
            or json_ld.get('description')
            or self._og_search_description(page, default=None)
        )

        # Duration from tracking data (in milliseconds) or JSON-LD
        duration = None
        av_duration_ms = traverse_obj(media_info, (
            'pluginData', 'tracking@all', 'avContent', 'av_content_duration'))
        if av_duration_ms:
            duration = int_or_none(av_duration_ms, scale=1000)
        if not duration:
            duration = json_ld.get('duration')

        # Upload date from JSON-LD
        upload_date = None
        upload_datetime = json_ld.get('upload_date') or traverse_obj(
            media_info, ('meta', 'broadcastedOnDateTime'))
        if upload_datetime:
            upload_date = unified_strdate(upload_datetime)

        # Thumbnail
        thumbnail = json_ld.get('thumbnail') or self._og_search_thumbnail(page, default=None)
        if not thumbnail:
            img_url = traverse_obj(media_info, ('meta', 'images', 0, 'url'))
            if img_url:
                img_url = img_url.replace('{size}', 'img__16__9__xl_-d31c35f8186ebeb80b0cd843a7c267a0e0c81647')
                thumbnail = self._proto_relative_url(img_url, 'https:')

        formats = []
        for stream in traverse_obj(media_info, ('streams', ...)):
            for media in traverse_obj(stream, ('media', ...)):
                media_url = url_or_none(self._proto_relative_url(media.get('url'), 'https:'))
                if not media_url:
                    continue

                mime_type = media.get('mimeType', '')

                if mime_type == 'application/vnd.apple.mpegurl' or media_url.endswith('.m3u8'):
                    formats.extend(self._extract_m3u8_formats(
                        media_url, video_id, 'mp4', m3u8_id='hls', fatal=False))
                elif mime_type == 'application/f4m+xml' or media_url.endswith('.f4m'):
                    formats.extend(self._extract_f4m_formats(
                        media_url, video_id, f4m_id='hds', fatal=False))
                else:
                    width = int_or_none(media.get('maxHResolutionPx'))
                    height = int_or_none(media.get('maxVResolutionPx'))
                    formats.append({
                        'url': media_url,
                        'width': width,
                        'height': height,
                        'vcodec': media.get('videoCodec'),
                        'format_id': 'http-%dx%d' % (width, height) if width and height else 'http',
                    })

        is_audio_only = traverse_obj(media_info, ('streams', 0, 'isAudioOnly'))

        return {
            'id': video_id,
            'title': title,
            'description': description,
            'thumbnail': thumbnail,
            'duration': duration,
            'upload_date': upload_date,
            'formats': formats,
            'vcodec': 'none' if is_audio_only else None,
        }


class BR24IE(InfoExtractor):
    IE_DESC = 'BR24 (Bayerischer Rundfunk Nachrichten)'
    _VALID_URL = r'https?://(?:www\.)?br\.de/nachrichten/(?:[a-z0-9\-]+/)?(?P<id>[a-z0-9\-]+,[A-Za-z0-9]+)'

    _TESTS = [
        {
            # Article with both AUDIO and VIDEO modules -> playlist
            'url': 'https://www.br.de/nachrichten/bayern/tod-von-hubert-aiwanger-erschuettert-seine-heimat-rottenburg,Va4aRPP',
            'info_dict': {
                'id': 'tod-von-hubert-aiwanger-erschuettert-seine-heimat-rottenburg,Va4aRPP',
                'title': 'Seine Heimat trauert: Aiwangers Tod erschüttert Rottenburg',
                'description': 'md5:2f67a4b588b9cef00853ff09271df77f',
            },
            'playlist_count': 2,
        },
        {
            # Article with AUDIO module (MP4 on cdn-storage.br.de)
            'url': 'https://www.br.de/nachrichten/deutschland-welt/junge-generation-wendet-sich-von-politischer-mitte-ab,Va4rpNw',
            'info_dict': {
                'id': '658b1fe3-db9d-4e29-9e6c-155899e6c520',
                'ext': 'mp4',
                'title': 'Die junge Generation fühlt sich in ihren Belangen von der politischen Mitte kaum vertreten. Wie aus dem ARD-DeutschlandTrend hervorgeht, sehen sich die Jungen bei Linker und AfD am besten repräsentiert - mit weitem Abstand zu Union, SPD und Grünen.',
                'description': 'md5:f7f45b5c90b67484df8b1d9bfcf81295',
                'thumbnail': r're:^https?://img\.br\.de/.+',
                'duration': 101,
                'vcodec': 'none',
                'upload_date': '20261105',
            },
        },
    ]

    def _real_extract(self, url):
        display_id = self._match_id(url)
        page = self._download_webpage(url, display_id)

        # BR24 is a Next.js app — all data is in __NEXT_DATA__
        next_data_str = self._search_regex(
            r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>',
            page, '__NEXT_DATA__')
        next_data = json.loads(next_data_str)

        article = traverse_obj(next_data, ('props', 'pageProps', 'article'))
        if not article:
            raise self._raise_no_formats('No article data found', video_id=display_id)

        title = article.get('title') or article.get('seoTitle') or display_id
        description = article.get('teaserText')
        thumbnail = traverse_obj(article, ('image', 'url'))
        upload_date = unified_strdate(article.get('publicationDate'))

        # Collect all VIDEO and AUDIO modules from the article
        entries = []
        for module in traverse_obj(article, ('modules', 'nodes', ...)):
            mod_type = module.get('type')

            if mod_type == 'VIDEO':
                video = module.get('video') or {}
                hls_url = video.get('hls')
                if not hls_url:
                    continue

                meta = {}
                if module.get('meta'):
                    try:
                        meta = json.loads(module['meta'])
                    except (ValueError, TypeError):
                        pass

                video_id = meta.get('assetId') or meta.get('sophoraId') or display_id
                formats = self._extract_m3u8_formats(hls_url, video_id, 'mp4', m3u8_id='hls', fatal=False)

                entries.append({
                    'id': video_id,
                    'title': module.get('title') or title,
                    'description': description,
                    'thumbnail': traverse_obj(module, ('thumbnail', 'url')) or thumbnail,
                    'duration': int_or_none(video.get('duration')),
                    'upload_date': upload_date,
                    'formats': formats,
                })

            elif mod_type == 'AUDIO':
                audio = module.get('audio') or {}
                audio_url = url_or_none(audio.get('url'))
                if not audio_url:
                    continue

                meta = {}
                if module.get('meta'):
                    try:
                        meta = json.loads(module['meta'])
                    except (ValueError, TypeError):
                        pass

                audio_id = meta.get('assetId') or meta.get('sophoraId') or display_id

                entries.append({
                    'id': audio_id,
                    'title': module.get('title') or title,
                    'description': description,
                    'thumbnail': traverse_obj(module, ('thumbnail', 'url')) or thumbnail,
                    'duration': int_or_none(audio.get('duration')),
                    'upload_date': upload_date,
                    'url': audio_url,
                    'vcodec': 'none',
                })

        if not entries:
            raise self._raise_no_formats('No media found in article', video_id=display_id)

        if len(entries) == 1:
            return entries[0]

        # Multiple media in one article → playlist
        return self.playlist_result(entries, display_id, title, description)
