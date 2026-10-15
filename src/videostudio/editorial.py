from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

import opentimelineio as otio

if TYPE_CHECKING:
    from videostudio.storage import StudioStorage


def construct_editorial_timeline(
    episode_id: str, shot_manifest: List[Dict[str, Any]]
) -> otio.schema.Timeline:
    """
    Constructs a multi-track OpenTimelineIO container mapping generated video clips,
    audio stems, editorial markers, and generative lineage metadata.
    """
    timeline = otio.schema.Timeline(name=f"Episode_{episode_id}_Assembly")
    video_track = otio.schema.Track(
        name="V1_Master_Video", kind=otio.schema.TrackKind.Video
    )
    dialogue_track = otio.schema.Track(
        name="A1_Dialogue", kind=otio.schema.TrackKind.Audio
    )

    current_time = otio.opentime.RationalTime(0, 24)

    for shot in shot_manifest:
        duration = otio.opentime.RationalTime(int(shot["duration_sec"] * 24), 24)
        time_range = otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24), duration=duration
        )

        # Instantiate video clip reference
        media_ref = otio.schema.ExternalReference(
            target_url=shot["video_path"],
            available_range=time_range,
        )
        clip = otio.schema.Clip(
            name=shot["shot_id"],
            media_reference=media_ref,
            source_range=time_range,
        )

        # Attach lineage and generation metadata
        clip.metadata["generative_lineage"] = {
            "prompt_uuid": shot["prompt_uuid"],
            "model_version": shot["model_version"],
            "seed": shot["seed"],
            "continuity_ledger_index": shot["ledger_idx"],
        }

        # Inject narrative marker
        marker = otio.schema.Marker(
            name=f"Beat: {shot['beat_name']}",
            marked_range=otio.opentime.TimeRange(
                start_time=current_time, duration=duration
            ),
            color=otio.schema.MarkerColor.CYAN,
        )
        clip.markers.append(marker)

        video_track.append(clip)

        # Populate synchronized dialogue audio track clip or gap
        audio_url = shot.get("audio_path")
        if audio_url:
            audio_ref = otio.schema.ExternalReference(
                target_url=audio_url,
                available_range=time_range,
            )
            audio_clip = otio.schema.Clip(
                name=f"{shot['shot_id']}_DLG",
                media_reference=audio_ref,
                source_range=time_range,
            )
            audio_clip.metadata["generative_lineage"] = {
                "prompt_uuid": shot["prompt_uuid"],
                "continuity_ledger_index": shot["ledger_idx"],
            }
            dialogue_track.append(audio_clip)
        else:
            gap = otio.schema.Gap(source_range=time_range)
            dialogue_track.append(gap)

        current_time += duration

    timeline.tracks.append(video_track)
    timeline.tracks.append(dialogue_track)
    return timeline


def export_timeline_otio(
    timeline: otio.schema.Timeline,
    storage: "StudioStorage",
    season: int,
    episode: int,
) -> Path:
    """Serialize an OpenTimelineIO timeline to season_XX/episode_YY/editorial/*.otio."""
    ep_dirs = storage.ensure_episode_directories(season, episode)
    filename = f"{timeline.name}.otio"
    target = ep_dirs["editorial"] / filename
    otio.adapters.write_to_file(timeline, str(target))
    return target


def timeline_to_summary_dict(timeline: otio.schema.Timeline) -> Dict[str, Any]:
    """Convert an OTIO timeline into a JSON-serializable summary for UI/API inspection."""
    tracks_summary: List[Dict[str, Any]] = []
    total_clips = 0
    total_frames = 0

    for track in timeline.tracks:
        items: List[Dict[str, Any]] = []
        for item in track:
            dur = item.source_range.duration if item.source_range else otio.opentime.RationalTime(0, 24)
            frames = int(dur.value)
            rate = float(dur.rate) if dur.rate else 24.0
            sec = round(frames / rate, 3)
            if isinstance(item, otio.schema.Clip):
                if track.kind == otio.schema.TrackKind.Video:
                    total_clips += 1
                    total_frames += frames
                target_url = (
                    item.media_reference.target_url
                    if isinstance(item.media_reference, otio.schema.ExternalReference)
                    else ""
                )
                markers = [
                    {"name": m.name, "color": m.color}
                    for m in getattr(item, "markers", [])
                ]
                items.append(
                    {
                        "type": "Clip",
                        "name": item.name,
                        "duration_seconds": sec,
                        "duration_frames": frames,
                        "target_url": target_url,
                        "generative_lineage": dict(item.metadata.get("generative_lineage", {})),
                        "markers": markers,
                    }
                )
            else:
                items.append(
                    {
                        "type": "Gap",
                        "duration_seconds": sec,
                        "duration_frames": frames,
                    }
                )
        tracks_summary.append(
            {
                "name": track.name,
                "kind": str(track.kind),
                "items": items,
            }
        )

    return {
        "name": timeline.name,
        "total_clips": total_clips,
        "total_frames": total_frames,
        "total_duration_seconds": round(total_frames / 24.0, 3),
        "tracks": tracks_summary,
    }
