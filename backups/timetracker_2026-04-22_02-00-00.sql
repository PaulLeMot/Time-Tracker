--
-- PostgreSQL database dump
--

\restrict fBicp5OYPjkPVTJlhsQhNOYMvwdteaMxg7pyWSAupj2d3a5rIVE7BhvfnXoMaSQ

-- Dumped from database version 15.17 (Debian 15.17-1.pgdg13+1)
-- Dumped by pg_dump version 17.9 (Debian 17.9-0+deb13u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
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
-- Name: employees; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.employees (
    id integer NOT NULL,
    full_name character varying NOT NULL,
    qr_code_secret character varying NOT NULL,
    is_active integer,
    password character varying
);


ALTER TABLE public.employees OWNER TO admin;

--
-- Name: employees_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.employees_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.employees_id_seq OWNER TO admin;

--
-- Name: employees_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.employees_id_seq OWNED BY public.employees.id;


--
-- Name: time_entries; Type: TABLE; Schema: public; Owner: admin
--

CREATE TABLE public.time_entries (
    id integer NOT NULL,
    employee_id integer,
    action character varying NOT NULL,
    "timestamp" timestamp without time zone NOT NULL,
    source character varying
);


ALTER TABLE public.time_entries OWNER TO admin;

--
-- Name: time_entries_id_seq; Type: SEQUENCE; Schema: public; Owner: admin
--

CREATE SEQUENCE public.time_entries_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.time_entries_id_seq OWNER TO admin;

--
-- Name: time_entries_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: admin
--

ALTER SEQUENCE public.time_entries_id_seq OWNED BY public.time_entries.id;


--
-- Name: employees id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employees ALTER COLUMN id SET DEFAULT nextval('public.employees_id_seq'::regclass);


--
-- Name: time_entries id; Type: DEFAULT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.time_entries ALTER COLUMN id SET DEFAULT nextval('public.time_entries_id_seq'::regclass);


--
-- Data for Name: employees; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.employees (id, full_name, qr_code_secret, is_active, password) FROM stdin;
1	челик челиков	3200a7aab4f04d5a	1	1234
2	йцу	c336f344e9024a6e	1	1111
\.


--
-- Data for Name: time_entries; Type: TABLE DATA; Schema: public; Owner: admin
--

COPY public.time_entries (id, employee_id, action, "timestamp", source) FROM stdin;
1	1	start	2026-04-19 08:34:00	admin
2	1	end	2026-04-19 23:51:00	admin
3	1	start	2026-04-19 17:07:29.029549	qr
4	2	start	2026-04-19 17:08:30.482873	qr
5	2	break_start	2026-04-19 17:08:32.871302	qr
6	2	break_end	2026-04-19 17:08:33.784074	qr
7	2	end	2026-04-19 17:08:34.514439	qr
8	1	start	2026-04-20 17:11:47.284008	qr
14	1	end	2026-04-20 23:22:00	admin
15	1	start	2026-04-21 13:55:37.934915	qr
16	1	break_start	2026-04-21 13:55:44.465328	qr
17	1	break_end	2026-04-21 13:55:45.397711	qr
18	1	end	2026-04-21 13:55:46.200322	qr
19	1	start	2026-04-21 14:02:07.127189	qr
20	1	end	2026-04-21 14:02:14.393926	qr
21	1	start	2026-04-21 14:02:15.627431	qr
22	1	break_start	2026-04-21 14:02:16.5267	qr
23	1	break_end	2026-04-21 14:02:18.693869	qr
24	1	break_start	2026-04-21 14:02:20.961442	qr
25	1	break_end	2026-04-21 14:02:21.827943	qr
26	1	break_start	2026-04-21 14:02:22.129181	qr
27	1	break_end	2026-04-21 14:02:22.427616	qr
28	1	break_start	2026-04-21 14:02:22.85896	qr
29	1	break_end	2026-04-21 14:02:35.558882	qr
30	1	end	2026-04-21 14:02:38.161942	qr
31	1	start	2026-04-21 14:03:07.12744	qr
32	1	end	2026-04-21 14:03:09.22789	qr
33	1	start	2026-04-21 18:52:07.478849	qr
34	1	break_start	2026-04-21 18:52:11.273333	qr
35	1	break_end	2026-04-21 18:52:21.222868	qr
36	1	end	2026-04-21 18:52:25.106289	qr
37	1	start	2026-04-21 18:55:09.418931	qr
38	1	break_start	2026-04-21 18:55:09.929174	qr
39	1	break_end	2026-04-21 19:25:06.462739	qr
40	1	break_start	2026-04-21 19:36:29.583351	qr
41	1	break_end	2026-04-21 19:36:32.189459	qr
42	1	break_start	2026-04-21 19:37:02.41903	qr
43	1	break_end	2026-04-22 01:28:01.977749	qr
44	1	break_start	2026-04-22 01:42:33.3884	qr
45	1	break_end	2026-04-22 01:42:50.221937	qr
46	1	end	2026-04-22 01:42:52.722768	qr
47	1	break_end	2026-04-22 02:44:00	admin
48	1	end	2026-04-22 01:48:12.319721	qr
49	1	end	2026-04-22 01:48:16.986209	qr
50	1	end	2026-04-22 01:48:17.717313	qr
51	1	end	2026-04-22 01:48:18.093767	qr
52	1	end	2026-04-22 01:48:18.482928	qr
53	1	end	2026-04-22 01:48:18.853505	qr
54	1	end	2026-04-22 01:48:19.246465	qr
55	1	end	2026-04-22 01:51:08.68635	qr
56	1	break_start	2026-04-22 01:51:19.38412	qr
57	1	break_start	2026-04-22 01:51:20.354677	qr
58	1	end	2026-04-22 01:51:21.420388	qr
59	1	break_start	2026-04-22 01:56:37.748016	qr
60	1	end	2026-04-22 01:56:39.180231	qr
\.


--
-- Name: employees_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.employees_id_seq', 2, true);


--
-- Name: time_entries_id_seq; Type: SEQUENCE SET; Schema: public; Owner: admin
--

SELECT pg_catalog.setval('public.time_entries_id_seq', 60, true);


--
-- Name: employees employees_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_pkey PRIMARY KEY (id);


--
-- Name: employees employees_qr_code_secret_key; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.employees
    ADD CONSTRAINT employees_qr_code_secret_key UNIQUE (qr_code_secret);


--
-- Name: time_entries time_entries_pkey; Type: CONSTRAINT; Schema: public; Owner: admin
--

ALTER TABLE ONLY public.time_entries
    ADD CONSTRAINT time_entries_pkey PRIMARY KEY (id);


--
-- Name: ix_employees_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX ix_employees_id ON public.employees USING btree (id);


--
-- Name: ix_time_entries_employee_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX ix_time_entries_employee_id ON public.time_entries USING btree (employee_id);


--
-- Name: ix_time_entries_id; Type: INDEX; Schema: public; Owner: admin
--

CREATE INDEX ix_time_entries_id ON public.time_entries USING btree (id);


--
-- PostgreSQL database dump complete
--

\unrestrict fBicp5OYPjkPVTJlhsQhNOYMvwdteaMxg7pyWSAupj2d3a5rIVE7BhvfnXoMaSQ

