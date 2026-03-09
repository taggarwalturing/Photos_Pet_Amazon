--
-- PostgreSQL database dump
--

\restrict c6ftYXN42QgABnpGeq1ZfDCzlSrnskeJVtlSmbOAL1Vv9ccWwQ2RYtthQDeeIGQ

-- Dumped from database version 14.19 (Homebrew)
-- Dumped by pg_dump version 14.19 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: annotation_selections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.annotation_selections (
    id integer NOT NULL,
    annotation_id integer NOT NULL,
    option_id integer NOT NULL
);


--
-- Name: annotation_selections_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.annotation_selections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: annotation_selections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.annotation_selections_id_seq OWNED BY public.annotation_selections.id;


--
-- Name: annotations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.annotations (
    id integer NOT NULL,
    image_id integer NOT NULL,
    annotator_id integer NOT NULL,
    category_id integer NOT NULL,
    is_duplicate boolean,
    status character varying(20) NOT NULL,
    time_spent_seconds integer NOT NULL,
    human_validated boolean NOT NULL,
    is_rework boolean NOT NULL,
    rework_time_seconds integer NOT NULL,
    review_status character varying(20),
    review_note text,
    reviewed_by integer,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: annotations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.annotations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: annotations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.annotations_id_seq OWNED BY public.annotations.id;


--
-- Name: annotator_categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.annotator_categories (
    id integer NOT NULL,
    user_id integer NOT NULL,
    category_id integer NOT NULL
);


--
-- Name: annotator_categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.annotator_categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: annotator_categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.annotator_categories_id_seq OWNED BY public.annotator_categories.id;


--
-- Name: categories; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.categories (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    display_order integer NOT NULL
);


--
-- Name: categories_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.categories_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: categories_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.categories_id_seq OWNED BY public.categories.id;


--
-- Name: drive_folders; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.drive_folders (
    id integer NOT NULL,
    folder_id character varying(255) NOT NULL,
    folder_name character varying(500),
    added_at timestamp with time zone DEFAULT now(),
    status character varying(50) NOT NULL,
    last_run_at timestamp with time zone,
    total_in_drive integer,
    downloaded_count integer,
    unique_count integer,
    duplicate_count integer,
    blurred_count integer,
    clean_count integer,
    failed_count integer,
    notes text,
    error_log text
);


--
-- Name: drive_folders_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.drive_folders_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: drive_folders_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.drive_folders_id_seq OWNED BY public.drive_folders.id;


--
-- Name: edit_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.edit_requests (
    id integer NOT NULL,
    user_id integer NOT NULL,
    image_id integer NOT NULL,
    reason text,
    status character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    reviewed_by integer,
    reviewed_at timestamp with time zone,
    review_note text
);


--
-- Name: edit_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.edit_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: edit_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.edit_requests_id_seq OWNED BY public.edit_requests.id;


--
-- Name: final_labels; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.final_labels (
    id integer NOT NULL,
    image_id integer NOT NULL,
    lighting_variation character varying(255),
    angle_perspective_variation character varying(255),
    environmental_context_variation character varying(255),
    occlusion_partial_visibility character varying(255),
    activity_motion character varying(255),
    multi_pet_disambiguation character varying(255),
    reviewer_name character varying(255),
    annotator_name character varying(255),
    approved_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: final_labels_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.final_labels_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: final_labels_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.final_labels_id_seq OWNED BY public.final_labels.id;


--
-- Name: images; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.images (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    original_filename character varying(255),
    original_format character varying(20),
    url character varying(1024) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    is_improper boolean NOT NULL,
    improper_reason text,
    marked_improper_by integer,
    marked_improper_at timestamp with time zone,
    compliance_processed boolean NOT NULL,
    compliance_status character varying(50),
    human_faces_detected integer NOT NULL,
    processing_log text,
    is_ai_generated boolean,
    ai_detection_confidence integer,
    marked_ai_by integer,
    marked_ai_at timestamp with time zone,
    human_visible boolean,
    human_visible_marked_by integer,
    human_visible_marked_at timestamp with time zone,
    original_url text,
    processed_url text,
    is_using_processed boolean NOT NULL,
    processing_method character varying(50),
    manually_blurred boolean NOT NULL,
    blur_regions json,
    manually_blurred_by integer,
    manually_blurred_at timestamp with time zone,
    annotated_blur_url text,
    source_drive_folder_id character varying(255),
    arbiter_labels json,
    arbiter_classified_at timestamp with time zone,
    image_drive_id character varying(255),
    is_blurred_annotator boolean DEFAULT false NOT NULL,
    is_restore_annotator boolean DEFAULT false NOT NULL,
    deliverable_image_path text,
    restored_by_annotator_id integer,
    restored_at_annotator timestamp with time zone,
    is_manually_modified boolean DEFAULT false NOT NULL,
    is_programmatically_blurred boolean DEFAULT false NOT NULL,
    is_duplicate boolean DEFAULT false NOT NULL,
    parent_image character varying(255),
    image_path text,
    gcs_folder character varying(20) DEFAULT 'input'::character varying
);


--
-- Name: images_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.images_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: images_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.images_id_seq OWNED BY public.images.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    message text,
    image_id integer,
    is_read boolean NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.options (
    id integer NOT NULL,
    category_id integer NOT NULL,
    label character varying(255) NOT NULL,
    is_typical boolean,
    display_order integer NOT NULL
);


--
-- Name: options_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.options_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: options_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.options_id_seq OWNED BY public.options.id;


--
-- Name: pipeline_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.pipeline_runs (
    id integer NOT NULL,
    status character varying,
    stage character varying,
    total_images integer,
    processed_images integer,
    failed_images integer,
    pending_images integer,
    unique_images integer,
    duplicate_images integer,
    duplicate_clusters integer,
    images_with_faces integer,
    images_without_faces integer,
    screenshots_skipped integer,
    current_stage_progress double precision,
    overall_progress double precision,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    estimated_completion timestamp without time zone,
    error_message text,
    error_details json,
    config json,
    logs json,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.pipeline_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.pipeline_runs_id_seq OWNED BY public.pipeline_runs.id;


--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_settings (
    id integer NOT NULL,
    key character varying(100) NOT NULL,
    value character varying(255) NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: system_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.system_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: system_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_settings_id_seq OWNED BY public.system_settings.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(255) NOT NULL,
    full_name character varying(255),
    role character varying(20) NOT NULL,
    is_active boolean,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: annotation_selections id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotation_selections ALTER COLUMN id SET DEFAULT nextval('public.annotation_selections_id_seq'::regclass);


--
-- Name: annotations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations ALTER COLUMN id SET DEFAULT nextval('public.annotations_id_seq'::regclass);


--
-- Name: annotator_categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotator_categories ALTER COLUMN id SET DEFAULT nextval('public.annotator_categories_id_seq'::regclass);


--
-- Name: categories id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories ALTER COLUMN id SET DEFAULT nextval('public.categories_id_seq'::regclass);


--
-- Name: drive_folders id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_folders ALTER COLUMN id SET DEFAULT nextval('public.drive_folders_id_seq'::regclass);


--
-- Name: edit_requests id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edit_requests ALTER COLUMN id SET DEFAULT nextval('public.edit_requests_id_seq'::regclass);


--
-- Name: final_labels id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.final_labels ALTER COLUMN id SET DEFAULT nextval('public.final_labels_id_seq'::regclass);


--
-- Name: images id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images ALTER COLUMN id SET DEFAULT nextval('public.images_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: options id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.options ALTER COLUMN id SET DEFAULT nextval('public.options_id_seq'::regclass);


--
-- Name: pipeline_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs ALTER COLUMN id SET DEFAULT nextval('public.pipeline_runs_id_seq'::regclass);


--
-- Name: system_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings ALTER COLUMN id SET DEFAULT nextval('public.system_settings_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: annotation_selections; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.annotation_selections (id, annotation_id, option_id) FROM stdin;
25	25	40
26	26	42
27	27	49
28	28	56
29	29	66
30	30	69
\.


--
-- Data for Name: annotations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.annotations (id, image_id, annotator_id, category_id, is_duplicate, status, time_spent_seconds, human_validated, is_rework, rework_time_seconds, review_status, review_note, reviewed_by, reviewed_at, created_at, updated_at) FROM stdin;
27	2836	8	9	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.645441+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.637571+05:30
28	2836	8	10	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.647192+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.638018+05:30
26	2836	8	8	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.644208+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.637218+05:30
25	2836	8	7	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.646349+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.636893+05:30
29	2836	8	11	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.649275+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.639479+05:30
30	2836	8	12	\N	completed	0	t	f	0	approved	\N	7	2026-03-09 18:49:11.669965+05:30	2026-03-09 18:48:51.728855+05:30	2026-03-09 18:49:11.661788+05:30
\.


--
-- Data for Name: annotator_categories; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.annotator_categories (id, user_id, category_id) FROM stdin;
25	8	7
26	8	8
27	8	9
28	8	10
29	8	11
30	8	12
\.


--
-- Data for Name: categories; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.categories (id, name, display_order) FROM stdin;
7	Lighting Variation	1
8	Angle & Perspective Variation	2
9	Environmental Context Variation	3
10	Occlusion & Partial Visibility	4
11	Activity & Motion	5
12	Multi-Pet Disambiguation	6
\.


--
-- Data for Name: drive_folders; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.drive_folders (id, folder_id, folder_name, added_at, status, last_run_at, total_in_drive, downloaded_count, unique_count, duplicate_count, blurred_count, clean_count, failed_count, notes, error_log) FROM stdin;
47	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	2026-03-09 18:40:32.815299+05:30	completed	2026-03-09 18:41:39.910517+05:30	0	11	0	0	0	11	0	Auto-discovered from GCS bucket	\N
\.


--
-- Data for Name: edit_requests; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.edit_requests (id, user_id, image_id, reason, status, created_at, reviewed_by, reviewed_at, review_note) FROM stdin;
\.


--
-- Data for Name: final_labels; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.final_labels (id, image_id, lighting_variation, angle_perspective_variation, environmental_context_variation, occlusion_partial_visibility, activity_motion, multi_pet_disambiguation, reviewer_name, annotator_name, approved_at, created_at, updated_at) FROM stdin;
5	2836	Well-lit conditions (typical)	Front-facing at eye level (typical)	Indoor setting (typical)	Full-body, unobstructed (typical)	Sleeping-curled up	Single pet (typical)	admin@turing.com	test@turing.com	2026-03-09 18:49:11.669965+05:30	2026-03-09 18:49:11.679174+05:30	2026-03-09 18:49:11.679174+05:30
\.


--
-- Data for Name: images; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.images (id, filename, original_filename, original_format, url, created_at, is_improper, improper_reason, marked_improper_by, marked_improper_at, compliance_processed, compliance_status, human_faces_detected, processing_log, is_ai_generated, ai_detection_confidence, marked_ai_by, marked_ai_at, human_visible, human_visible_marked_by, human_visible_marked_at, original_url, processed_url, is_using_processed, processing_method, manually_blurred, blur_regions, manually_blurred_by, manually_blurred_at, annotated_blur_url, source_drive_folder_id, arbiter_labels, arbiter_classified_at, image_drive_id, is_blurred_annotator, is_restore_annotator, deliverable_image_path, restored_by_annotator_id, restored_at_annotator, is_manually_modified, is_programmatically_blurred, is_duplicate, parent_image, image_path, gcs_folder) FROM stdin;
2835	1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1IVHePKDTlLNM5b7TRREdQrFYOSSSfAS2.jpg	clean
2837	1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "two_similar"}	2026-03-09 18:43:42.071994+05:30	1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1xdEA4pPGgnIThrHVZ3DTvl8sWl47Ngze.jpg	clean
2838	1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "None", "activity": "None", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1yXPPkNGNHEyPeu6YbRr-PxOGuQ-aNvYl.jpg	clean
2839	1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "top_down", "environment": "indoor", "occlusion": "None", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1kEgNhaZcJpbpg-2pl8wp7b6BEIbE9B2h.jpg	clean
2840	1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "None", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1jBBXFSwpzBfRNWNtRbZR5UE6TpJ0jeeb.jpg	clean
2841	1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "two_similar"}	2026-03-09 18:43:42.071994+05:30	1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Xc02tjjtOAHniSFKjgV50IDFTWOx_vBV.jpg	clean
2842	1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "harsh_sunlight", "viewpoint": "top_down", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "two_similar"}	2026-03-09 18:43:42.071994+05:30	1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1Aiok9pFVEC0qdr3oN-AGYCFBf4u7St-7.jpg	clean
2845	16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	16DI-XApmK6B_O97T50ke0vo2i85CYkJj	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/16DI-XApmK6B_O97T50ke0vo2i85CYkJj.jpg	clean
2843	1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "None", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1XPuJxShUZfwVnZIhfgCgL6AdU2GKdsXC.jpg	clean
2844	1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	t	\N	f	\N	\N	\N	\N	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sitting_posed", "multipet": "single_pet"}	2026-03-09 18:44:13.440003+05:30	1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF	f	f	\N	\N	\N	f	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1rzOYkFqNTtU4to3K-BO5j-lDSieQOLdF.jpg	clean
2836	1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	2026-03-09 18:41:39.645507+05:30	f	\N	\N	\N	t	clean	0	Action: no_face, Faces: 0	\N	\N	\N	\N	\N	\N	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	t	\N	t	[{"x": 0.07623525372650372, "y": 0.7018056509244424, "width": 0.8007858321332862, "height": 0.2916711172147199}]	7	2026-03-09 13:17:07.288029+05:30	gs://annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/blur/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ	{"lighting": "well_lit", "viewpoint": "front_eye_level", "environment": "indoor", "occlusion": "full_body", "activity": "sleeping", "multipet": "single_pet"}	2026-03-09 18:43:42.071994+05:30	1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X	f	f	annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/blur/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	\N	\N	t	f	f	\N	gs://amazon-photo-pets-test/annotated/1iy8BUGGaLS-XzFzIzY5zH6MyqzDl04lQ/clean/1nvnXc25mqKh9UbT9QpwFq6J1jY2qA94X.jpg	blur
\.


--
-- Data for Name: notifications; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.notifications (id, user_id, type, title, message, image_id, is_read, created_at) FROM stdin;
\.


--
-- Data for Name: options; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.options (id, category_id, label, is_typical, display_order) FROM stdin;
37	7	Dusk-dawn lighting	f	1
38	7	Harsh outdoor sunlight with shadows	f	2
39	7	Low light conditions	f	3
40	7	Well-lit conditions (typical)	t	4
41	7	None of the Above	f	5
42	8	Front-facing at eye level (typical)	t	1
43	8	Ground-level view	f	2
44	8	No head showing	f	3
45	8	Partial view (head only)	f	4
46	8	Top-down view	f	5
47	8	None of the Above	f	6
48	9	In car-carrier	f	1
49	9	Indoor setting (typical)	t	2
50	9	Outdoor dirt road	f	3
51	9	Snow environment	f	4
52	9	Vet clinic	f	5
53	9	Yard with a complex background	f	6
54	9	None of the Above	f	7
55	10	Behind furniture (face only)	f	1
56	10	Full-body, unobstructed (typical)	t	2
57	10	Partially hidden under a blanket	f	3
58	10	Peeking out of box-carrier	f	4
59	10	Toy obscuring part of body	f	5
60	10	None of the Above	f	6
61	11	Eating-drinking	f	1
62	11	Jumping to catch toy	f	2
63	11	Playing with another pet	f	3
64	11	Running with motion blur	f	4
65	11	Sitting still-posed (typical)	t	5
66	11	Sleeping-curled up	f	6
67	11	None of the Above	f	7
68	12	Pet with breed lookalike	f	1
69	12	Single pet (typical)	t	2
70	12	Three pets of same breed	f	3
71	12	Two similar-looking pets together	f	4
72	12	None of the Above	f	5
\.


--
-- Data for Name: pipeline_runs; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.pipeline_runs (id, status, stage, total_images, processed_images, failed_images, pending_images, unique_images, duplicate_images, duplicate_clusters, images_with_faces, images_without_faces, screenshots_skipped, current_stage_progress, overall_progress, started_at, completed_at, estimated_completion, error_message, error_details, config, logs, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: system_settings; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.system_settings (id, key, value, updated_at) FROM stdin;
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.users (id, username, password_hash, full_name, role, is_active, created_at) FROM stdin;
7	admin@turing.com	$2b$12$QJcMWS5.lOGzYqdwHg2VdOOWMq3YMjpFET.ZxkWr9fSr8SYZMIPT6	Administrator	admin	t	2026-03-09 18:38:00.985679+05:30
8	test@turing.com	$2b$12$hhDcAImINfpoWvUynMLYQOG.ZnP9x2vTlQmUNIEelbuw7HzawSBom	test	annotator	t	2026-03-09 18:48:16.588632+05:30
\.


--
-- Name: annotation_selections_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.annotation_selections_id_seq', 30, true);


--
-- Name: annotations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.annotations_id_seq', 30, true);


--
-- Name: annotator_categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.annotator_categories_id_seq', 30, true);


--
-- Name: categories_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.categories_id_seq', 12, true);


--
-- Name: drive_folders_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.drive_folders_id_seq', 47, true);


--
-- Name: edit_requests_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.edit_requests_id_seq', 1, false);


--
-- Name: final_labels_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.final_labels_id_seq', 5, true);


--
-- Name: images_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.images_id_seq', 2845, true);


--
-- Name: notifications_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.notifications_id_seq', 1, false);


--
-- Name: options_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.options_id_seq', 72, true);


--
-- Name: pipeline_runs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.pipeline_runs_id_seq', 1, false);


--
-- Name: system_settings_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.system_settings_id_seq', 1, false);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.users_id_seq', 8, true);


--
-- Name: annotation_selections annotation_selections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotation_selections
    ADD CONSTRAINT annotation_selections_pkey PRIMARY KEY (id);


--
-- Name: annotations annotations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_pkey PRIMARY KEY (id);


--
-- Name: annotator_categories annotator_categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotator_categories
    ADD CONSTRAINT annotator_categories_pkey PRIMARY KEY (id);


--
-- Name: categories categories_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_name_key UNIQUE (name);


--
-- Name: categories categories_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.categories
    ADD CONSTRAINT categories_pkey PRIMARY KEY (id);


--
-- Name: drive_folders drive_folders_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_folders
    ADD CONSTRAINT drive_folders_pkey PRIMARY KEY (id);


--
-- Name: edit_requests edit_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edit_requests
    ADD CONSTRAINT edit_requests_pkey PRIMARY KEY (id);


--
-- Name: final_labels final_labels_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.final_labels
    ADD CONSTRAINT final_labels_pkey PRIMARY KEY (id);


--
-- Name: images images_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: options options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.options
    ADD CONSTRAINT options_pkey PRIMARY KEY (id);


--
-- Name: pipeline_runs pipeline_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.pipeline_runs
    ADD CONSTRAINT pipeline_runs_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (id);


--
-- Name: annotation_selections uq_annotation_option; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotation_selections
    ADD CONSTRAINT uq_annotation_option UNIQUE (annotation_id, option_id);


--
-- Name: annotator_categories uq_annotator_category; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotator_categories
    ADD CONSTRAINT uq_annotator_category UNIQUE (user_id, category_id);


--
-- Name: annotations uq_image_annotator_category; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT uq_image_annotator_category UNIQUE (image_id, annotator_id, category_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: idx_annotations_annotator_updated; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_annotations_annotator_updated ON public.annotations USING btree (annotator_id, updated_at);


--
-- Name: idx_annotations_image_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_annotations_image_category ON public.annotations USING btree (image_id, category_id);


--
-- Name: idx_annotations_review_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_annotations_review_status ON public.annotations USING btree (review_status) WHERE (review_status IS NOT NULL);


--
-- Name: idx_annotator_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_annotator_status ON public.annotations USING btree (annotator_id, status);


--
-- Name: idx_compliance_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_compliance_status ON public.images USING btree (compliance_processed, compliance_status);


--
-- Name: idx_image_annotator; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_image_annotator ON public.annotations USING btree (image_id, annotator_id);


--
-- Name: idx_image_drive_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_image_drive_id ON public.images USING btree (image_drive_id);


--
-- Name: idx_images_compliance; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_images_compliance ON public.images USING btree (compliance_status);


--
-- Name: idx_images_deliverable; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_images_deliverable ON public.images USING btree (deliverable_image_path) WHERE (deliverable_image_path IS NOT NULL);


--
-- Name: idx_images_filename; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_images_filename ON public.images USING btree (filename);


--
-- Name: idx_images_manually_blurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_images_manually_blurred ON public.images USING btree (manually_blurred) WHERE (manually_blurred = true);


--
-- Name: idx_improper_created; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_improper_created ON public.images USING btree (is_improper, created_at);


--
-- Name: idx_status_review; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_status_review ON public.annotations USING btree (status, review_status);


--
-- Name: ix_annotation_selections_annotation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotation_selections_annotation_id ON public.annotation_selections USING btree (annotation_id);


--
-- Name: ix_annotation_selections_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotation_selections_id ON public.annotation_selections USING btree (id);


--
-- Name: ix_annotation_selections_option_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotation_selections_option_id ON public.annotation_selections USING btree (option_id);


--
-- Name: ix_annotations_annotator_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_annotator_id ON public.annotations USING btree (annotator_id);


--
-- Name: ix_annotations_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_category_id ON public.annotations USING btree (category_id);


--
-- Name: ix_annotations_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_id ON public.annotations USING btree (id);


--
-- Name: ix_annotations_image_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_image_id ON public.annotations USING btree (image_id);


--
-- Name: ix_annotations_review_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_review_status ON public.annotations USING btree (review_status);


--
-- Name: ix_annotations_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_status ON public.annotations USING btree (status);


--
-- Name: ix_annotations_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotations_updated_at ON public.annotations USING btree (updated_at);


--
-- Name: ix_annotator_categories_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_annotator_categories_id ON public.annotator_categories USING btree (id);


--
-- Name: ix_categories_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_categories_id ON public.categories USING btree (id);


--
-- Name: ix_drive_folders_folder_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_drive_folders_folder_id ON public.drive_folders USING btree (folder_id);


--
-- Name: ix_drive_folders_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_folders_id ON public.drive_folders USING btree (id);


--
-- Name: ix_edit_requests_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_edit_requests_id ON public.edit_requests USING btree (id);


--
-- Name: ix_final_labels_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_final_labels_id ON public.final_labels USING btree (id);


--
-- Name: ix_final_labels_image_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_final_labels_image_id ON public.final_labels USING btree (image_id);


--
-- Name: ix_images_compliance_processed; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_images_compliance_processed ON public.images USING btree (compliance_processed);


--
-- Name: ix_images_compliance_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_images_compliance_status ON public.images USING btree (compliance_status);


--
-- Name: ix_images_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_images_id ON public.images USING btree (id);


--
-- Name: ix_images_is_improper; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_images_is_improper ON public.images USING btree (is_improper);


--
-- Name: ix_images_source_drive_folder_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_images_source_drive_folder_id ON public.images USING btree (source_drive_folder_id);


--
-- Name: ix_notifications_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notifications_id ON public.notifications USING btree (id);


--
-- Name: ix_options_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_options_id ON public.options USING btree (id);


--
-- Name: ix_pipeline_runs_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pipeline_runs_id ON public.pipeline_runs USING btree (id);


--
-- Name: ix_pipeline_runs_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_pipeline_runs_status ON public.pipeline_runs USING btree (status);


--
-- Name: ix_system_settings_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_settings_id ON public.system_settings USING btree (id);


--
-- Name: ix_system_settings_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_system_settings_key ON public.system_settings USING btree (key);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: annotation_selections annotation_selections_annotation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotation_selections
    ADD CONSTRAINT annotation_selections_annotation_id_fkey FOREIGN KEY (annotation_id) REFERENCES public.annotations(id) ON DELETE CASCADE;


--
-- Name: annotation_selections annotation_selections_option_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotation_selections
    ADD CONSTRAINT annotation_selections_option_id_fkey FOREIGN KEY (option_id) REFERENCES public.options(id);


--
-- Name: annotations annotations_annotator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_annotator_id_fkey FOREIGN KEY (annotator_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: annotations annotations_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;


--
-- Name: annotations annotations_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(id) ON DELETE CASCADE;


--
-- Name: annotations annotations_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotations
    ADD CONSTRAINT annotations_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: annotator_categories annotator_categories_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotator_categories
    ADD CONSTRAINT annotator_categories_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id) ON DELETE CASCADE;


--
-- Name: annotator_categories annotator_categories_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.annotator_categories
    ADD CONSTRAINT annotator_categories_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: edit_requests edit_requests_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edit_requests
    ADD CONSTRAINT edit_requests_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(id) ON DELETE CASCADE;


--
-- Name: edit_requests edit_requests_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edit_requests
    ADD CONSTRAINT edit_requests_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: edit_requests edit_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.edit_requests
    ADD CONSTRAINT edit_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: final_labels final_labels_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.final_labels
    ADD CONSTRAINT final_labels_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(id) ON DELETE CASCADE;


--
-- Name: images images_human_visible_marked_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_human_visible_marked_by_fkey FOREIGN KEY (human_visible_marked_by) REFERENCES public.users(id);


--
-- Name: images images_manually_blurred_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_manually_blurred_by_fkey FOREIGN KEY (manually_blurred_by) REFERENCES public.users(id);


--
-- Name: images images_marked_ai_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_marked_ai_by_fkey FOREIGN KEY (marked_ai_by) REFERENCES public.users(id);


--
-- Name: images images_marked_improper_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_marked_improper_by_fkey FOREIGN KEY (marked_improper_by) REFERENCES public.users(id);


--
-- Name: images images_restored_by_annotator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.images
    ADD CONSTRAINT images_restored_by_annotator_id_fkey FOREIGN KEY (restored_by_annotator_id) REFERENCES public.users(id);


--
-- Name: notifications notifications_image_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_image_id_fkey FOREIGN KEY (image_id) REFERENCES public.images(id) ON DELETE SET NULL;


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: options options_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.options
    ADD CONSTRAINT options_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.categories(id);


--
-- PostgreSQL database dump complete
--

\unrestrict c6ftYXN42QgABnpGeq1ZfDCzlSrnskeJVtlSmbOAL1Vv9ccWwQ2RYtthQDeeIGQ

