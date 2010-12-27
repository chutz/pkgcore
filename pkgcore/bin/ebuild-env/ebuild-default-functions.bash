#!/bin/bash
# ebuild-default-functions.sh; default functions for ebuild env that aren't saved- specific to the portage instance.
# Copyright 2005-2010 Brian Harring <ferringb@gmail.com>: BSD/GPL2
# Copyright 2004-2006 Gentoo Foundation: GPL2

portageq() {
	if [[ $EBUILD_PHASE == depend ]]; then
		die "portageq calls in depends phase is disallowed"
	fi
	PYTHONPATH="$PKGCORE_PYTHONPATH" PORTAGEQ_LIMIT_EAPI="${EAPI:--1}" \
		"${PKGCORE_PYTHON_BINARY}" "${PKGCORE_BIN_PATH}/portageq_emulation" \
		--domain "${PKGCORE_DOMAIN}" "$@"
}

has_version()
{
	portageq 'has_version' "${ROOT}" "$1"
}

best_version()
{
	portageq 'best_version' "${ROOT}" "$1"
}

# adds ".keep" files so that dirs aren't auto-cleaned
keepdir()
{
	dodir "$@"
	local x
	if [ "$1" == "-R" ] || [ "$1" == "-r" ]; then
		shift
		find "$@" -type d -printf "${D}/%p/.keep\0" | $XARGS -0 -n100 touch || die "Failed to recursive create .keep files"
	else
		for x in "$@"; do
			touch "${D}/${x}/.keep" || die "Failed to create .keep in ${D}/${x}"
		done
	fi
}

# sandbox support functions
addread()
{
	export SANDBOX_READ="$SANDBOX_READ:$1"
}

addwrite()
{
	export SANDBOX_WRITE="$SANDBOX_WRITE:$1"
}

adddeny()
{
	export SANDBOX_DENY="$SANDBOX_DENY:$1"
}

addpredict()
{
	export SANDBOX_PREDICT="$SANDBOX_PREDICT:$1"
}

unpack()
{
	local x y myfail srcdir taropts tar_subdir
	taropts='--no-same-owner'

	[ -z "$*" ] && die "Nothing passed to the 'unpack' command"

	for x in "$@"; do
		echo ">>> Unpacking ${x} to ${PWD}"
		myfail="failure unpacking ${x}"
		y="${x%.*}"
		y="${y##*.}"
		if [ "${x:0:2}" == "./" ]; then
			srcdir=''
		else
			srcdir="${DISTDIR}"
		fi

		[ ! -s "${srcdir}${x}" ] && die "$myfail: empty file"
		[ "${x/${DISTDIR}}" != "${x}" ] && \
			die "Arguments to unpack() should not begin with \${DISTDIR}."

		case "${x}" in
			*.tar)
				tar xf "${srcdir}${x}" ${taropts} || die "$myfail"
				;;
			*.tar.gz|*.tgz|*.tar.Z)
				tar xzf "${srcdir}${x}" ${taropts} || die "$myfail"
				;;
			*.tar.bz2|*.tbz2|*.tbz)
				bzip2 -dc "${srcdir}${x}" | tar xf - ${taropts}
				assert "$myfail"
				;;
			*.tar.xz)
				if hasq "$EAPI" 0 1 2; then
					echo "xv is a supported extension in eapi3 and above only" >&2
					continue;
				fi
				xz -dc "${srcdir}${x}" | tar xf - ${taropts} || die "$myfail"
				;;
			*.ZIP|*.zip|*.jar)
				unzip -qo "${srcdir}${x}" || die "$myfail"
				;;
			*.gz|*.Z|*.z)
				gzip -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				;;
			*.bz2|*.bz)
				bzip2 -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				;;
			*.xz)
				if hasq "$EAPI" 0 1 2; then
					echo "xv is a supported extension in eapi3 and above only" >&2
					continue;
				fi
				xz -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				;;
			*.7Z|*.7z)
				local my_output
				my_output="$(7z x -y "${srcdir}/${x}")"
				if [ $? -ne 0 ]; then
					echo "${my_output}" >&2
					die "$myfail"
				fi
				;;
			*.RAR|*.rar)
				unrar x -idq -o+ "${srcdir}/${x}" || die "$myfail"
				;;
			*.LHa|*.LHA|*.lha|*.lzh)
				lha xfq "${srcdir}/${x}" || die "$myfail"
				;;
			*.a|*.deb)
				ar x "${srcdir}/${x}" || die "$myfail"
				;;
			*.lzma)
				if [ "${y}" == "tar" ]; then
					lzma -dc "${srcdir}${x}" | tar xof - ${taropts}
					assert "$myfail"
				else
					lzma -dc "${srcdir}${x}" > ${x%.*} || die "$myfail"
				fi
				;;
			*)
				echo "unpack ${x}: file format not recognized. Ignoring."
				;;
		esac
	done
	find . -mindepth 1 -maxdepth 1 ! -type l -print0 | \
		 ${XARGS} -0 chmod -fR a+rX,u+w,g-w,o-w

}

dyn_setup()
{
	MUST_EXPORT_ENV="yes"
	pkg_setup
}

dyn_unpack()
{
	local newstuff="no"
	MUST_EXPORT_ENV="yes"
	if [ -e "${WORKDIR}" ]; then
		local x
		local checkme
		for x in ${AA}; do
			echo ">>> Checking ${x}'s mtime..."
			if [ "${DISTDIR}/${x}" -nt "${WORKDIR}" ]; then
				echo ">>> ${x} has been updated; recreating WORKDIR..."
				newstuff="yes"
				rm -rf "${WORKDIR}"
				break
			fi
		done
		if [ "${EBUILD}" -nt "${WORKDIR}" ]; then
			echo ">>> ${EBUILD} has been updated; recreating WORKDIR..."
			newstuff="yes"
			rm -rf "${WORKDIR}"
		fi
	fi

	cd "${WORKDIR}"
	src_unpack
}

abort_handler()
{
	local msg
	if [ "$2" != "fail" ]; then
		msg="${EBUILD}: ${1} aborted; exiting."
	else
		msg="${EBUILD}: ${1} failed; exiting."
	fi
	echo
	echo "$msg"
	echo
	eval ${3}
	#unset signal handler
}

abort_compile()
{
	abort_handler "src_compile" $1
	exit 1
}

abort_unpack()
{
	abort_handler "src_unpack" $1
	exit 1
}

abort_package()
{
	abort_handler "dyn_package" $1
	rm -f "${PKGDIR}"/All/${PF}.t*
	exit 1
}

abort_test()
{
	abort_handler "dyn_test" $1
	exit 1
}

abort_install()
{
	abort_handler "src_install" $1
	exit 1
}

dyn_compile()
{
	MUST_EXPORT_ENV="yes"
	export DESTTREE=/usr
	export INSDESTTREE=""
	export EXEDESTTREE=""
	export DOCDESTTREE=""
	export INSOPTIONS="-m0644"
	export EXEOPTIONS="-m0755"
	export LIBOPTIONS="-m0644"
	export DIROPTIONS="-m0755"
	export MOPREFIX=${PN}

	[ "${CFLAGS-unset}"      != "unset" ] && export CFLAGS
	[ "${CXXFLAGS-unset}"    != "unset" ] && export CXXFLAGS
	[ "${LIBCFLAGS-unset}"   != "unset" ] && export LIBCFLAGS
	[ "${LIBCXXFLAGS-unset}" != "unset" ] && export LIBCXXFLAGS
	[ "${LDFLAGS-unset}"     != "unset" ] && export LDFLAGS
	[ "${ASFLAGS-unset}"     != "unset" ] && export ASFLAGS

	[ ! -z "${DISTCC_DIR}" ] && addwrite "${DISTCC_DIR}"

	if [ -d "${S}" ]; then
		cd "${S}"
	else
		# cd to some random dir that we at least control.
		cd "${WORKDIR}"
	fi
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages use an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	src_compile
	#|| abort_compile "fail"
	if has nostrip $FEATURES $RESTRICT; then
		touch DEBUGBUILD
	fi
}

dyn_configure()
{
	MUST_EXPORT_ENV="yes"
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "$WORKDIR"
	fi
	src_configure
}

dyn_prepare()
{
	MUST_EXPORT_ENV="yes"
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "$WORKDIR"
	fi
	src_prepare
}

dyn_test()
{
		echo ">>> Test phase [enabled]: ${CATEGORY}/${PF}"
		MUST_EXPORT_ENV="yes"
		if [ -d "${S}" ]; then
			cd "${S}"
		else
			cd "${WORKDIR}"
		fi
		src_test
}


dyn_install()
{
	rm -rf "${D}"
	mkdir "${D}"
	if [ -d "${S}" ]; then
		cd "${S}"
	else
		cd "$WORKDIR"
	fi
	echo
	echo ">>> Install ${PF} into ${D} category ${CATEGORY}"
	#our custom version of libtool uses $S and $D to fix
	#invalid paths in .la files
	export S D
	#some packages uses an alternative to $S to build in, cause
	#our libtool to create problematic .la files
	export PWORKDIR="$WORKDIR"
	src_install
	#|| abort_install "fail"
	prepall
	cd "${D}"

	if type -p scanelf > /dev/null ; then
		# Make sure we disallow insecure RUNPATH/RPATH's
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.
		f=$(scanelf -qyRF '%r %p' "${D}" | grep -E "(${WORKDIR}|${D}|: |::|^ )")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain insecure RUNPATH's"
			echo " Please file a bug about this at http://bugs.gentoo.org/"
			echo " For more information on this issue, kindly review:"
			echo " http://bugs.gentoo.org/81745"
			echo "${f}"
			echo -ne '\a\n'
			has stricter $FEATURES && die "Insecure binaries detected"
			echo "autofixing rpath..."
			TMPDIR="${WORKDIR}" scanelf -BXr ${f} -o /dev/null
		fi

		# Check for setid binaries but are not built with BIND_NOW
		f=$(scanelf -qyRF '%b %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files are setXid, dyn linked, and using lazy bindings"
			echo " This combination is generally discouraged.  Try re-emerging the package:"
			echo " LDFLAGS='-Wl,-z,now' emerge ${PN}"
			echo "${f}"
			echo -ne '\a\n'
			has stricter $FEATURES && die "Aborting due to lazy bindings"
			sleep 1
		fi

		# TEXTREL's are baaaaaaaad
		f=$(scanelf -qyRF '%t %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain runtime text relocations"
			echo " Text relocations require a lot of extra work to be preformed by the"
			echo " dynamic linker which will cause serious performance impact on IA-32"
			echo " and might not function properly on other architectures hppa for example."
			echo " If you are a programmer please take a closer look at this package and"
			echo " consider writing a patch which addresses this problem."
			echo "${f}"
			echo -ne '\a\n'
			has stricter $FEATURES && die "Aborting due to textrels"
			sleep 1
		fi

		# Check for files with executable stacks
		f=$(scanelf -qyRF '%e %p' "${D}")
		if [[ -n ${f} ]] ; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain executable stacks"
			echo " Files with executable stacks will not work properly (or at all!)"
			echo " on some architectures/operating systems.  A bug should be filed"
			echo " at http://bugs.gentoo.org/ to make sure the file is fixed."
			echo "${f}"
			echo -ne '\a\n'
			has stricter $FEATURES && die "Aborting due to +x stack"
			sleep 1
		fi

		# disabled by harring; we don't use it currently.
		# Save NEEDED information
		#scanelf -qyRF '%p %n' "${D}" | sed -e 's:^:/:' > "${T}/NEEDED"
	fi

	echo ">>> Completed installing ${PF} into ${D}"
	echo
	unset dir
	MUST_EXPORT_ENV="yes"
}

dyn_postinst()
{
	pkg_postinst
}

dyn_preinst()
{
	# set IMAGE depending if this is a binary or compile merge
	local IMAGE=${D}

	# Make sure D is where the package expects it
	D=${IMAGE} pkg_preinst

	# total suid control.
	if has suidctl $FEATURES > /dev/null ; then
		sfconf=/etc/portage/suidctl.conf
		echo ">>> Preforming suid scan in ${IMAGE}"
		for i in $(find "${IMAGE}"/ -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [ -s "${sfconf}" ]; then
				suid=$(grep ^${i/${IMAGE}/}$ ${sfconf})
				if [ "${suid}" = "${i/${IMAGE}/}" ]; then
					echo "- ${i/${IMAGE}/} is an approved suid file"
				else
					echo ">>> Removing sbit on non registered ${i/${IMAGE}/}"
					sleepbeep 6
					chmod ugo-s "${i}"
					grep ^#${i/${IMAGE}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						echo ">>> Appending commented out entry to ${sfconf} for ${PF}"
						ls_ret=`ls -ldh "${i}"`
						echo "## ${ls_ret%${IMAGE}*}${ls_ret#*${IMAGE}}" >> ${sfconf}
						echo "#${i/${IMAGE}/}" >> ${sfconf}
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				echo "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi

	# SELinux file labeling (needs to always be last in dyn_preinst)
	if has selinux $FEATURES || use selinux; then
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [ -f /selinux/context -a -x /usr/sbin/setfiles ]; then
			echo ">>> Setting SELinux security labels"
			if [ -f ${POLICYDIR}/file_contexts/file_contexts ]; then
				cp -f "${POLICYDIR}/file_contexts/file_contexts" "${T}"
			else
				make -C "${POLICYDIR}" FC=${T}/file_contexts "${T}/file_contexts"
			fi

			addwrite /selinux/context
			/usr/sbin/setfiles -r "${IMAGE}" "${T}/file_contexts" "${IMAGE}" \
				|| die "Failed to set SELinux security labels."
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			echo "!!! Unable to set SELinux security labels"
		fi
	fi
	MUST_EXPORT_ENV="yes"
}


# debug-print() gets called from many places with verbose status information useful
# for tracking down problems. The output is in $T/eclass-debug.log.
# You can set ECLASS_DEBUG_OUTPUT to redirect the output somewhere else as well.
# The special "on" setting echoes the information, mixing it with the rest of the
# emerge output.
# You can override the setting by exporting a new one from the console, or you can
# set a new default in make.*. Here the default is "" or unset.

# in the future might use e* from /etc/init.d/functions.sh if i feel like it
debug-print()
{
	if has ${EBUILD_PHASE} depend nofetch config info postinst; then
		return
	fi
	# if $T isn't defined, we're in dep calculation mode and
	# shouldn't do anything
	[ -z "$T" ] && return 0

	while [ "$1" ]; do

		# extra user-configurable targets
		if [ "$ECLASS_DEBUG_OUTPUT" == "on" ]; then
			echo "debug: $1"
		elif [ -n "$ECLASS_DEBUG_OUTPUT" ]; then
			echo "debug: $1" >> $ECLASS_DEBUG_OUTPUT
		fi

		# default target
		echo "$1" >> "${T}/eclass-debug.log"
		# let the portage user own/write to this file
		chmod g+w "${T}/eclass-debug.log" &>/dev/null

		shift
	done
}

# The following 2 functions are debug-print() wrappers

debug-print-function()
{
	str="$1: entering function"
	shift
	debug-print "$str, parameters: $*"
}

debug-print-section()
{
	debug-print "now in section $*"
}


internal_inherit()
{
	# default, backwards compatible beast.
	local location overlay
	location="${ECLASSDIR}/${1}.eclass"

	if [ -n "$PORTDIR_OVERLAY" ]; then
		local overlay
		for overlay in ${PORTDIR_OVERLAY}; do
			if [ -e "${overlay}/eclass/${1}.eclass" ]; then
				location="${overlay}/eclass/${1}.eclass"
				debug-print "  eclass exists: ${location}"
			fi
		done
	fi
	debug-print "inherit: $1 -> $location"
	source "$location" >&2 || die "died sourcing $location in inherit()"
	return 0
}

# Sources all eclasses in parameters
declare -ix ECLASS_DEPTH=0
inherit()
{
	local SAVED_INHERIT_COUNT=0

	if [[ $ECLASS_DEPTH < 0 ]] && [ "${EBUILD_PHASE}" == "depend" ]; then
		#echo "QA Notice: ${CATEGORY}/${PF} makes multiple inherit calls: $*" >&2
		SAVED_INHERIT_COUNT=$ECLASS_DEPTH
		ECLASS_DEPTH=0
	fi
	ECLASS_DEPTH=$(($ECLASS_DEPTH + 1))
	if [[ $ECLASS_DEPTH > 1 ]]; then
		debug-print "*** Multiple Inheritence (Level: ${ECLASS_DEPTH})"
	fi

	local location olocation
	local PECLASS

	local B_IUSE
	local B_DEPEND
	local B_RDEPEND
	local B_PDEPEND
	while [ -n "$1" ]; do

		# PECLASS is used to restore the ECLASS var after recursion.
		PECLASS="$ECLASS"
		export ECLASS="$1"

		if [ "$EBUILD_PHASE" != "depend" ]; then
			if ! has $ECLASS $INHERITED; then
				echo
				echo "QA Notice: ECLASS '$ECLASS' illegal conditional inherit in $CATEGORY/$PF" >&2
				echo
			fi
		fi

		#We need to back up the value of DEPEND and RDEPEND to B_DEPEND and B_RDEPEND
		#(if set).. and then restore them after the inherit call.

		#turn off glob expansion
		set -f

		# Retain the old data and restore it later.
		unset B_IUSE B_DEPEND B_RDEPEND B_PDEPEND
		[ "${IUSE-unset}"    != "unset" ] && B_IUSE="${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && B_DEPEND="${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && B_RDEPEND="${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && B_PDEPEND="${PDEPEND}"
		unset   IUSE   DEPEND   RDEPEND   PDEPEND
		#turn on glob expansion
		set +f
		if ! internal_inherit "$1"; then
			die "failed sourcing $1 in inherit()"
		fi

		#turn off glob expansion
		set -f

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[ "${IUSE-unset}"    != "unset" ] && export E_IUSE="${E_IUSE} ${IUSE}"
		[ "${DEPEND-unset}"  != "unset" ] && export E_DEPEND="${E_DEPEND} ${DEPEND}"
		[ "${RDEPEND-unset}" != "unset" ] && export E_RDEPEND="${E_RDEPEND} ${RDEPEND}"
		[ "${PDEPEND-unset}" != "unset" ] && export E_PDEPEND="${E_PDEPEND} ${PDEPEND}"

		[ "${B_IUSE-unset}"    != "unset" ] && IUSE="${B_IUSE}"
		[ "${B_IUSE-unset}"    != "unset" ] || unset IUSE

		[ "${B_DEPEND-unset}"  != "unset" ] && DEPEND="${B_DEPEND}"
		[ "${B_DEPEND-unset}"  != "unset" ] || unset DEPEND

		[ "${B_RDEPEND-unset}" != "unset" ] && RDEPEND="${B_RDEPEND}"
		[ "${B_RDEPEND-unset}" != "unset" ] || unset RDEPEND

		[ "${B_PDEPEND-unset}" != "unset" ] && PDEPEND="${B_PDEPEND}"
		[ "${B_PDEPEND-unset}" != "unset" ] || unset PDEPEND

		#turn on glob expansion
		set +f

		if ! has $1 $INHERITED; then
			INHERITED="$INHERITED $ECLASS"
		fi
		export ECLASS="$PECLASS"

		shift
	done
	ECLASS_DEPTH=$(($ECLASS_DEPTH - 1))
	if [[ $ECLASS_DEPTH == 0 ]]; then
		ECLASS_DEPTH=$(($SAVED_INHERIT_COUNT - 1))
	fi
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS()
{
	if [ -z "$ECLASS" ]; then
		echo "EXPORT_FUNCTIONS without a defined ECLASS" >&2
		exit 1
	fi
	while [ "$1" ]; do
		debug-print "EXPORT_FUNCTIONS: ${1} -> ${ECLASS}_${1}"
		eval "$1() { ${ECLASS}_$1 "\$@" ; }" > /dev/null
		shift
	done
}

# this is a function for removing any directory matching a passed in pattern from
# PATH
remove_path_entry()
{
	save_IFS
	IFS=":"
	stripped_path="${PATH}"
	while [ -n "$1" ]; do
		cur_path=""
		for p in ${stripped_path}; do
			if [ "${p/${1}}" == "${p}" ]; then
				cur_path="${cur_path}:${p}"
			fi
		done
		stripped_path="${cur_path#:*}"
		shift
	done
	restore_IFS
	PATH="${stripped_path}"
}

QA_INTERCEPTORS="javac java-config python python-config perl grep egrep fgrep sed gcc g++ cc bash awk nawk pkg-config"
enable_qa_interceptors()
{

	# Turn of extended glob matching so that g++ doesn't get incorrectly matched.
	shopt -u extglob

	# QA INTERCEPTORS
	local FUNC_SRC BIN BODY BIN_PATH
	for BIN in ${QA_INTERCEPTORS}; do
		BIN_PATH=$(type -pf ${BIN})
		if [ "$?" != "0" ]; then
			BODY="echo \"*** missing command: ${BIN}\" >&2; return 127"
		else
			BODY="${BIN_PATH} \"\$@\"; return \$?"
		fi
		FUNC_SRC="function ${BIN}() {
			echo -n \"QA Notice: ${BIN} in global scope: \" >&2
			if [ \$ECLASS_DEPTH -gt 0 ]; then
				echo \"eclass \${ECLASS}\" >&2
			else
				echo \"\${CATEGORY}/\${PF}\" >&2
			fi
			${BODY}
		}";
		eval "$FUNC_SRC" || echo "error creating QA interceptor ${BIN}" >&2
	done
}

disable_qa_interceptors()
{
	for x in $QA_INTERCEPTORS; do
		unset -f $x
	done
}

useq()
{
	local u="${1}"
	local neg=0
	if [ "${u:0:1}" == "!" ]; then
		u="${u:1}"
		neg=1
	fi
	local x

	# Make sure we have this USE flag in IUSE
	# temp disable due to PORTAGE_ARCHLIST not being exported in
	#if ! has "${u}" ${IUSE} ${E_IUSE} && ! hasq "${u}" ${PORTAGE_ARCHLIST} selinux; then
	#    echo "QA Notice: USE Flag '${u}' not in IUSE for ${CATEGORY}/${PF}" >&2
	#fi

	for x in ${USE}; do
		if [ "${x}" == "${u}" ]; then
			if [ ${neg} -eq 1 ]; then
				return 1
			else
				return 0
			fi
		fi
	done
	if [ ${neg} -eq 1 ]; then
		return 0
	else
		return 1
	fi
}

usev()
{
	if useq ${1}; then
		echo "${1}"
		return 0
	fi
	return 1
}

insopts()
{
	INSOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			INSOPTIONS="$INSOPTIONS $x"
		fi
	done
	export INSOPTIONS
}

diropts()
{
	DIROPTIONS=""
	for x in $*; do
		DIROPTIONS="${DIROPTIONS} $x"
	done
	export DIROPTIONS
}

exeopts()
{
	EXEOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			EXEOPTIONS="$EXEOPTIONS $x"
		fi
	done
	export EXEOPTIONS
}

libopts()
{
	LIBOPTIONS=""
	for x in $*; do
		#if we have a debug build, let's not strip anything
		if has nostrip $FEATURES $RESTRICT && [ "$x" == "-s" ]; then
			continue
		else
			LIBOPTIONS="$LIBOPTIONS $x"
		fi
	done
	export LIBOPTIONS
}

DONT_EXPORT_VARS="${DONT_EXPORT_VARS} ECLASS_DEPTH"
true